#!/usr/bin/env Rscript
# n1_glmm.R — N1: the logistic mixed models of F.3 / F.4 / F.5, fitted with lme4::glmer (Laplace).
#
# Why R: statsmodels (F.8's first choice) has no maximum-likelihood binomial mixed model — its only
# binomial GLMM (BinomialBayesMixedGLM) is a variational-Bayes approximation with no likelihood-based
# Wald tests — so F.8's registered fallback, R/lme4, fits every logistic mixed model.
#
# Called by n1_analysis.py:   Rscript n1_glmm.R <jobs.json> <out.json>
# Each job: {"id", "data" (CSV with columns query, arm, y), "arms" (levels, first = reference),
#            "contrasts" [[a, b], ...] meaning a - b, "boot" (CSV of cluster-resample counts or null)}
# Model per job (one subject model, one outcome):  y ~ arm + (1 | query), binomial(logit), nAGQ = 1.
# job$re = "query+cell" instead fits y ~ arm + (1 | query) + (1 | query:arm) — the declared
# heterogeneity sensitivity (query-by-arm variation in the outcome, which the registered model omits).
#
# Convergence protocol (fixed before any real fit):
#   0. not identifiable if any arm has all y = 0 or all y = 1 (complete separation)  -> status "separation"
#   1. bobyqa (maxfun 2e5); a fit "converges" when lme4's convergence checks raise no warning other
#      than a singular-fit (boundary) message; singular fits are kept and flagged;
#   2. if not: Nelder_Mead (maxfun 2e5); 3. if not: nlminbwrap;
#   4. if none converges -> status "failed" (the caller applies the registered F.3 fallback).
# Wald contrasts: estimate L b, SE sqrt(L V L'), z, two-sided p, 95% CI estimate +/- 1.959964 SE.
# Optional cluster bootstrap of the contrasts: each replicate re-fits the same model on the resampled
# queries (a query drawn k times enters as k distinct clusters), bobyqa, derivatives not computed;
# replicates that are separated or error are dropped and counted; percentile 2.5/97.5 (type 7).
# Replicates run in parallel where the platform forks (results do not depend on the core count).
suppressPackageStartupMessages({ library(lme4); library(jsonlite) })

args <- commandArgs(trailingOnly = TRUE)
jobs <- fromJSON(args[1], simplifyVector = FALSE)
out <- list()

conv_msgs <- function(fit) {
  m <- fit@optinfo$conv$lme4$messages
  if (is.null(m)) character(0) else as.character(m)
}
is_conv_problem <- function(msgs) {
  msgs <- msgs[!grepl("singular", msgs, ignore.case = TRUE)]
  length(msgs) > 0
}
fit_one <- function(d, optimizer, derivs = TRUE, form = y ~ arm + (1 | query)) {
  warn <- character(0)
  fit <- withCallingHandlers(
    tryCatch(glmer(form, data = d, family = binomial, nAGQ = 1,
                   control = glmerControl(optimizer = optimizer, calc.derivs = derivs,
                                          optCtrl = if (optimizer == "nlminbwrap") list() else list(maxfun = 2e5))),
             error = function(e) e),
    warning = function(w) { warn <<- c(warn, conditionMessage(w)); invokeRestart("muffleWarning") })
  list(fit = fit, warn = warn)
}
contrast_table <- function(fit, arms, contrasts) {
  b <- fixef(fit); V <- as.matrix(vcov(fit)); nm <- names(b)
  res <- list()
  for (cc in contrasts) {
    L <- setNames(rep(0, length(b)), nm)
    for (k in 1:2) {
      a <- cc[[k]]; s <- if (k == 1) 1 else -1
      if (a != arms[[1]]) L[paste0("arm", a)] <- L[paste0("arm", a)] + s
    }
    est <- sum(L * b); se <- sqrt(as.numeric(t(L) %*% V %*% L))
    z <- est / se; p <- 2 * pnorm(-abs(z))
    res[[paste(cc[[1]], cc[[2]], sep = "-")]] <- list(estimate = est, se = se, z = z, p = p,
                                                        ci_low = est - 1.959964 * se, ci_high = est + 1.959964 * se)
  }
  res
}

for (job in jobs) {
  d <- read.csv(job$data, stringsAsFactors = FALSE)
  arms <- unlist(job$arms)
  d$arm <- factor(d$arm, levels = arms)
  d$query <- factor(d$query)
  r <- list(id = job$id, n = nrow(d), n_query = nlevels(d$query))
  sep <- any(sapply(arms, function(a) { v <- d$y[d$arm == a]; length(v) == 0 || all(v == 0) || all(v == 1) }))
  r$events <- lapply(setNames(arms, arms), function(a) list(y1 = sum(d$y[d$arm == a]), n = sum(d$arm == a)))
  if (sep) {
    r$status <- "separation"; out[[length(out) + 1]] <- r; next
  }
  chosen <- NULL
  tried <- list()
  form <- if (!is.null(job$re) && job$re == "query+cell") y ~ arm + (1 | query) + (1 | query:arm) else y ~ arm + (1 | query)
  r$formula <- deparse(form)
  for (opt in c("bobyqa", "Nelder_Mead", "nlminbwrap")) {
    f <- fit_one(d, opt, form = form)
    if (inherits(f$fit, "error")) { tried[[opt]] <- paste("error:", conditionMessage(f$fit)); next }
    msgs <- unique(c(conv_msgs(f$fit), f$warn))
    tried[[opt]] <- if (length(msgs)) msgs else "ok"
    if (!is_conv_problem(msgs)) { chosen <- list(opt = opt, fit = f$fit, msgs = msgs); break }
  }
  r$tried <- tried
  if (is.null(chosen)) { r$status <- "failed"; out[[length(out) + 1]] <- r; next }
  fit <- chosen$fit
  r$status <- "ok"; r$optimizer <- chosen$opt; r$singular <- isSingular(fit)
  r$random_intercept_sd <- as.numeric(attr(VarCorr(fit)$query, "stddev"))
  if (!is.null(VarCorr(fit)[["query:arm"]])) r$cell_sd <- as.numeric(attr(VarCorr(fit)[["query:arm"]], "stddev"))
  r$fixef <- as.list(fixef(fit))
  r$contrasts <- contrast_table(fit, arms, job$contrasts)
  if (!is.null(job$boot)) {
    cnt <- as.matrix(read.csv(job$boot, header = FALSE))      # B x nq counts, columns = sorted query ids
    qids <- unlist(job$boot_queries)
    keys <- names(r$contrasts)
    by_q <- split(seq_len(nrow(d)), as.character(d$query))
    rows_q <- lapply(qids, function(q) if (is.null(by_q[[q]])) integer(0) else by_q[[q]])
    size_q <- vapply(rows_q, length, 0L)
    one <- function(bi) {
      k <- cnt[bi, ]
      idx <- unlist(rep(rows_q, k), use.names = FALSE)
      if (!length(idx)) return(NULL)
      cl <- rep(seq_len(sum(k)), times = rep(size_q, k))
      db <- d[idx, , drop = FALSE]; db$query <- factor(cl)
      if (any(vapply(arms, function(a) { v <- db$y[db$arm == a]; length(v) == 0 || all(v == 0) || all(v == 1) }, TRUE)))
        return(NULL)
      fb <- suppressWarnings(tryCatch(glmer(form, data = db, family = binomial, nAGQ = 1,
                                            control = glmerControl(optimizer = "bobyqa", calc.derivs = FALSE)),
                                      error = function(e) NULL))
      if (is.null(fb)) return(NULL)
      ct <- contrast_table(fb, arms, job$contrasts)
      vapply(keys, function(k2) ct[[k2]]$estimate, 0)
    }
    ncore <- max(1L, parallel::detectCores(logical = TRUE))
    reps <- if (.Platform$OS.type == "unix" && ncore > 1) parallel::mclapply(seq_len(nrow(cnt)), one, mc.cores = ncore)
            else lapply(seq_len(nrow(cnt)), one)
    ok <- vapply(reps, function(x) is.numeric(x) && length(x) == length(keys) && all(is.finite(x)), TRUE)
    rep_est <- if (any(ok)) do.call(rbind, reps[ok]) else matrix(NA_real_, 0, length(keys), dimnames = list(NULL, keys))
    if (is.null(dim(rep_est))) rep_est <- matrix(rep_est, ncol = length(keys), dimnames = list(NULL, keys))
    colnames(rep_est) <- keys
    r$boot <- list(B = nrow(cnt), dropped = sum(!ok),
                   ci = lapply(setNames(keys, keys), function(k2) {
                     v <- rep_est[, k2]; v <- v[is.finite(v)]
                     as.list(quantile(v, c(0.025, 0.975), names = FALSE, type = 7)) }))
  }
  out[[length(out) + 1]] <- r
}
writeLines(toJSON(out, auto_unbox = TRUE, digits = NA, null = "null", na = "null"), args[2])

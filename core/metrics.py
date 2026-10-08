"""DDIV Experiment Evaluation Metrics and Aggregation Module.

Defines data models and computation routines for:
- Task Success Rate (TSR)
- Pass@1
- Repair Accuracy
- Regression Rate
- Recovery Success Rate
- Failure Detection Precision, Recall, and F1 (Macro and Per-Class F1-F4)
- Average & Median Repair Time
- Token Usage and Inference Cost
- Confusion Matrix for Fault Taxonomy
"""

from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field


class ClassMetric(BaseModel):
    """Precision, recall, and F1 for a specific failure class."""

    class_name: str
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1: Optional[float] = None


class ConfusionMatrixResult(BaseModel):
    """Confusion matrix and classification metrics across F1-F4 taxonomy."""

    classes: List[str] = Field(default_factory=lambda: ["F1", "F2", "F3", "F4"])
    matrix: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    per_class: Dict[str, ClassMetric] = Field(default_factory=dict)
    macro_precision: Optional[float] = None
    macro_recall: Optional[float] = None
    macro_f1: Optional[float] = None
    total_samples: int = 0
    unlabeled_samples: int = 0


class TaskEvaluationMetrics(BaseModel):
    """Per-task evaluation metrics matching the DDIV specification."""

    pass_at_1: bool = False
    repair_accuracy: Optional[bool] = None
    regression_detected: bool = False
    recovery_triggered: Optional[bool] = None
    recovery_success: Optional[bool] = None
    repair_time_seconds: float = 0.0
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    inference_calls: int = 0
    inference_cost_usd: Optional[float] = None
    agent_timings: Dict[str, float] = Field(default_factory=dict)
    model_invocations: List[Dict[str, Any]] = Field(default_factory=list)
    # Extended DDIV metrics
    context_characters: Optional[int] = None
    critic_approved: Optional[bool] = None
    critic_risk_level: Optional[str] = None
    memory_retrieved: Optional[bool] = None


class FailureDetectionRecord(BaseModel):
    """Failure detection record matching the per-task JSON schema specification."""

    predicted_category: Optional[str] = None
    actual_category: Optional[str] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1: Optional[float] = None


class ConditionAggregateMetrics(BaseModel):
    """Aggregate evaluation metrics across all tasks for an experimental condition."""

    condition: str
    total_tasks: int = 0
    resolved_tasks: int = 0
    tsr: float = 0.0
    pass_at_1_tasks: int = 0
    pass_at_1_rate: float = 0.0

    # Repair accuracy counts
    total_patches_generated: int = 0
    invalid_or_empty_patches: int = 0
    valid_patches_count: int = 0
    valid_incorrect_patches: int = 0
    correct_patches_count: int = 0
    repair_accuracy: Optional[float] = None

    # Regression counts
    valid_evaluated_patches_count: int = 0
    regression_patches_count: int = 0
    regression_rate: Optional[float] = None

    # Recovery counts
    recovery_events_attempted: Optional[int] = None
    recovery_events_successful: Optional[int] = None
    recovery_success_rate: Optional[float] = None
    recovery_gain: Optional[float] = None

    # Timing
    repair_times: List[float] = Field(default_factory=list)
    mean_repair_time_seconds: float = 0.0
    median_repair_time_seconds: float = 0.0
    average_attempts: float = 0.0

    # Tokens and calls
    total_input_tokens: Optional[int] = None
    total_output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    average_total_tokens: Optional[float] = None
    total_inference_calls: int = 0
    average_inference_calls: float = 0.0
    total_inference_cost_usd: Optional[float] = None

    # Classification
    failure_detection: Optional[ConfusionMatrixResult] = None
    failure_distribution: Dict[str, int] = Field(default_factory=dict)

    # Extended DDIV mechanism metrics
    patch_critic_rejection_rate: Optional[float] = None
    memory_retrieval_rate: Optional[float] = None
    memory_assisted_recovery_rate: Optional[float] = None
    average_context_characters: Optional[float] = None
    agent_invocation_counts: Dict[str, int] = Field(default_factory=dict)


def determine_actual_failure_category(attempt_data: Dict[str, Any]) -> Optional[str]:
    """Objectively determine the ground-truth failure category from execution evidence.

    F1 = Localization failure (located files empty or localization error)
    F2 = Reasoning/code logic failure (valid patch applied to localized code, but tests failed)
    F3 = Tool/syntax/patch execution failure (PatchBuilder error, invalid diff, apply failed)
    F4 = Coordination/timeout failure (timeout or agent coordination abort)

    If objective ground-truth cannot be established unambiguously, returns None.
    """
    if attempt_data.get("internal_resolved", False) is True:
        return None

    # 1. Check F4: Operational / timeout failure
    if attempt_data.get("timed_out") is True or attempt_data.get("timeout") is True:
        return "F4"
    test_status = str(attempt_data.get("agent_test_status", "") or "").upper()
    if test_status in ("TIMEOUT", "EXECUTION_TIMEOUT"):
        return "F4"
    err_str = str(attempt_data.get("error", "") or "").lower()
    if "timed out" in err_str or "timeout" in err_str:
        return "F4"

    # 2. Check F1: Localization failure
    if attempt_data.get("locator_error_code"):
        return "F1"
    located_files = attempt_data.get("located_files")
    if located_files is not None and len(located_files) == 0 and not attempt_data.get("patch_valid", False):
        return "F1"

    # 3. Check F3: Tool / patch synthesis / syntax / git apply failure
    coder_err = attempt_data.get("coder_error_code")
    if coder_err in (
        "PATCH_BUILDER_FAILED",
        "CODER_EMPTY_RESPONSE",
        "CODER_INVALID_JSON",
        "CODER_SCHEMA_FAILURE",
        "CODER_NO_VALID_MODIFICATION",
    ):
        return "F3"

    if attempt_data.get("patch_valid") is False:
        return "F3"

    if attempt_data.get("agent_apply_success") is False:
        return "F3"

    val_err = attempt_data.get("patch_validation_error")
    if val_err and "empty" in str(val_err).lower():
        return "F3"

    # 4. Check F1 vs F2: Patch was valid and applied cleanly, but tests failed
    patch_valid = attempt_data.get("patch_valid", False)
    apply_success = attempt_data.get("agent_apply_success", False)
    f2p_passed = attempt_data.get("f2p_passed", False)

    if patch_valid and apply_success and not f2p_passed:
        if located_files is not None and len(located_files) == 0:
            return "F1"
        return "F2"

    return None


def compute_task_metrics(record_data: Union[BaseModel, Dict[str, Any]]) -> TaskEvaluationMetrics:
    """Compute task-level evaluation metrics from an ExperimentConditionRecord or JSON dict."""
    data = record_data.model_dump() if hasattr(record_data, "model_dump") else dict(record_data)
    attempt_history = data.get("attempt_history", [])
    cond = str(data.get("condition", "")).lower()
    is_full_ddiv = "full_ddiv" in cond

    # 1. PASS@1
    pass_at_1 = False
    if attempt_history:
        first_att = attempt_history[0]
        pass_at_1 = bool(first_att.get("internal_resolved", False))

    # 2. Repair Accuracy for final patch
    final_patch_correct: Optional[bool] = None
    if attempt_history:
        last_att = attempt_history[-1]
        p_valid = last_att.get("patch_valid")
        f2p = last_att.get("f2p_passed")
        p2p = last_att.get("p2p_passed")
        if p_valid is True:
            final_patch_correct = bool(f2p is True and p2p is True)
        elif p_valid is False:
            final_patch_correct = False
        else:
            final_patch_correct = None

    # 3. Regression Detected across any attempt with a valid evaluated patch
    regression_detected = False
    for att in attempt_history:
        if att.get("patch_valid") is True and att.get("agent_apply_success") is True:
            if att.get("p2p_passed") is False:
                regression_detected = True
                break

    # 4. Recovery Triggered & Success (DDIV specific)
    recovery_triggered: Optional[bool] = None
    recovery_success: Optional[bool] = None

    if is_full_ddiv:
        num_attempts = len(attempt_history)
        if num_attempts > 1:
            recovery_triggered = True
            recovery_success = any(
                bool(attempt_history[i].get("internal_resolved", False))
                for i in range(1, num_attempts)
            )
        else:
            recovery_triggered = False
            recovery_success = None
    else:
        recovery_triggered = False
        recovery_success = None

    # 5. Timing
    repair_time = float(data.get("execution_duration_seconds", 0.0) or 0.0)

    # 6. Tokens & Invocations
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    inference_calls = 0
    invocations: List[Dict[str, Any]] = []
    agent_timings: Dict[str, float] = {}

    has_token_data = False
    sum_in = 0
    sum_out = 0
    sum_tot = 0

    for att in attempt_history:
        tok_data = att.get("token_usage") or {}
        if tok_data:
            has_token_data = True
            sum_in += tok_data.get("prompt_tokens", 0) or 0
            sum_out += tok_data.get("completion_tokens", 0) or 0
            sum_tot += tok_data.get("total_tokens", 0) or 0

        att_invocs = att.get("model_invocations", [])
        if att_invocs:
            invocations.extend(att_invocs)
            inference_calls += len(att_invocs)
        else:
            step_count = 0
            if att.get("coder_proposals") or att.get("generated_patch") or att.get("coder_error_code"):
                step_count += 2
            if att.get("agent_test_status") is not None:
                step_count += 1
            if att.get("failure_category") or att.get("recovery_strategy"):
                step_count += 1
            inference_calls += max(step_count, 1)

        timings = att.get("agent_timings") or {}
        for k, v in timings.items():
            agent_timings[k] = agent_timings.get(k, 0.0) + float(v or 0.0)

    if has_token_data:
        input_tokens = sum_in
        output_tokens = sum_out
        total_tokens = sum_tot

    context_chars = None
    critic_approved = None
    critic_risk = None
    mem_retrieved = None

    if attempt_history:
        first_att = attempt_history[0]
        context_chars = first_att.get("context_characters")
        if context_chars is None and first_att.get("source_files"):
            context_chars = len(first_att.get("source_files"))
        
        last_att = attempt_history[-1]
        critic_data = last_att.get("patch_critic") or {}
        if critic_data:
            critic_approved = critic_data.get("approved")
            critic_risk = critic_data.get("risk_level")
        
        mem_retrieved = any(att.get("memory_retrieved", False) or bool(att.get("memory_context")) for att in attempt_history)

    return TaskEvaluationMetrics(
        pass_at_1=pass_at_1,
        repair_accuracy=final_patch_correct,
        regression_detected=regression_detected,
        recovery_triggered=recovery_triggered,
        recovery_success=recovery_success,
        repair_time_seconds=round(repair_time, 2),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        inference_calls=inference_calls,
        inference_cost_usd=None,
        agent_timings=agent_timings,
        model_invocations=invocations,
        context_characters=context_chars,
        critic_approved=critic_approved,
        critic_risk_level=critic_risk,
        memory_retrieved=mem_retrieved,
    )


def compute_task_failure_detection(
    record_data: Union[BaseModel, Dict[str, Any]]
) -> Optional[FailureDetectionRecord]:
    """Extract failure detection record (predicted vs actual) for a task."""
    data = record_data.model_dump() if hasattr(record_data, "model_dump") else dict(record_data)
    attempt_history = data.get("attempt_history", [])
    if not attempt_history:
        return None

    predicted = None
    actual = None
    for att in attempt_history:
        pred_cat = att.get("failure_category")
        if pred_cat and pred_cat in ("F1", "F2", "F3", "F4"):
            predicted = pred_cat
            actual = determine_actual_failure_category(att)
            break

    if predicted is None:
        return None

    return FailureDetectionRecord(
        predicted_category=predicted,
        actual_category=actual,
        precision=None,
        recall=None,
        f1=None,
    )


def compute_confusion_matrix(
    samples: List[Tuple[Optional[str], Optional[str]]]
) -> Optional[ConfusionMatrixResult]:
    """Compute confusion matrix and Precision/Recall/F1 for F1-F4 classification."""
    classes = ["F1", "F2", "F3", "F4"]
    matrix: Dict[str, Dict[str, int]] = {c: {p: 0 for p in classes} for c in classes}
    valid_samples = []
    unlabeled_count = 0

    for pred, act in samples:
        if act is None:
            unlabeled_count += 1
            continue
        if pred in classes and act in classes:
            valid_samples.append((pred, act))
            matrix[act][pred] += 1

    if not valid_samples and unlabeled_count == 0:
        return None

    per_class: Dict[str, ClassMetric] = {}
    precisions: List[float] = []
    recalls: List[float] = []
    f1s: List[float] = []

    for c in classes:
        tp = matrix[c][c]
        fp = sum(matrix[other][c] for other in classes if other != c)
        fn = sum(matrix[c][other] for other in classes if other != c)
        tn = sum(
            matrix[o1][o2]
            for o1 in classes
            for o2 in classes
            if o1 != c and o2 != c
        )

        prec = tp / (tp + fp) if (tp + fp) > 0 else None
        rec = tp / (tp + fn) if (tp + fn) > 0 else None
        if prec is not None and rec is not None and (prec + rec) > 0:
            f1_val = 2 * prec * rec / (prec + rec)
        elif prec is not None and rec is not None:
            f1_val = 0.0
        else:
            f1_val = None

        per_class[c] = ClassMetric(
            class_name=c,
            tp=tp,
            fp=fp,
            fn=fn,
            tn=tn,
            precision=round(prec, 4) if prec is not None else None,
            recall=round(rec, 4) if rec is not None else None,
            f1=round(f1_val, 4) if f1_val is not None else None,
        )

        if prec is not None:
            precisions.append(prec)
        if rec is not None:
            recalls.append(rec)
        if f1_val is not None:
            f1s.append(f1_val)

    macro_p = sum(precisions) / len(precisions) if precisions else None
    macro_r = sum(recalls) / len(recalls) if recalls else None
    macro_f1 = sum(f1s) / len(f1s) if f1s else None

    return ConfusionMatrixResult(
        classes=classes,
        matrix=matrix,
        per_class=per_class,
        macro_precision=round(macro_p, 4) if macro_p is not None else None,
        macro_recall=round(macro_r, 4) if macro_r is not None else None,
        macro_f1=round(macro_f1, 4) if macro_f1 is not None else None,
        total_samples=len(valid_samples),
        unlabeled_samples=unlabeled_count,
    )


def aggregate_condition_metrics(
    records: List[Union[BaseModel, Dict[str, Any]]], condition_name: str
) -> ConditionAggregateMetrics:
    """Aggregate all task records for a specific experiment condition."""
    cond_clean = condition_name.strip().lower()
    is_baseline = "baseline" in cond_clean
    is_retry_only = "retry_only" in cond_clean
    is_full_ddiv = "full_ddiv" in cond_clean

    total_tasks = len(records)
    if total_tasks == 0:
        return ConditionAggregateMetrics(condition=condition_name)

    resolved_count = 0
    pass_at_1_count = 0
    attempts_list: List[int] = []
    repair_times: List[float] = []

    total_patches = 0
    invalid_or_empty_count = 0
    valid_patches_count = 0
    valid_incorrect_count = 0
    correct_patches_count = 0

    valid_evaluated_count = 0
    regression_count = 0

    recovery_events_attempted = 0
    recovery_events_successful = 0

    total_in_tok = 0
    total_out_tok = 0
    total_tok = 0
    has_any_token_data = False
    total_calls = 0
    total_cost: Optional[float] = None

    diagnosis_samples: List[Tuple[Optional[str], Optional[str]]] = []

    for r in records:
        data = r.model_dump() if hasattr(r, "model_dump") else dict(r)
        is_resolved = bool(data.get("resolved", False))
        if is_resolved:
            resolved_count += 1

        attempts = int(data.get("attempts", 0) or 0)
        attempts_list.append(attempts)

        dur = float(data.get("execution_duration_seconds", 0.0) or 0.0)
        repair_times.append(dur)

        att_hist = data.get("attempt_history", [])
        if att_hist:
            if bool(att_hist[0].get("internal_resolved", False)):
                pass_at_1_count += 1

            for idx, att in enumerate(att_hist):
                p_valid = att.get("patch_valid")
                p_gen = bool(att.get("generated_patch", "").strip())
                apply_success = att.get("agent_apply_success", False)
                f2p = att.get("f2p_passed", False)
                p2p = att.get("p2p_passed", False)

                total_patches += 1
                if not p_gen or p_valid is False:
                    invalid_or_empty_count += 1
                elif p_valid is True:
                    valid_patches_count += 1
                    if f2p is True and p2p is True:
                        correct_patches_count += 1
                    else:
                        valid_incorrect_count += 1

                if p_valid is True and apply_success is True:
                    valid_evaluated_count += 1
                    if p2p is False:
                        regression_count += 1

                if is_full_ddiv and idx > 0:
                    prev_att = att_hist[idx - 1]
                    if not prev_att.get("internal_resolved", False) and prev_att.get("failure_category"):
                        recovery_events_attempted += 1
                        if att.get("internal_resolved", False):
                            recovery_events_successful += 1

                # Diagnosis samples for confusion matrix
                if is_full_ddiv and att.get("failure_category"):
                    pred = att.get("failure_category")
                    act = determine_actual_failure_category(att)
                    diagnosis_samples.append((pred, act))

        # Task-level metrics (tokens, calls, cost)
        task_metrics = data.get("metrics")
        if not task_metrics:
            task_metrics = compute_task_metrics(data).model_dump()

        if task_metrics.get("total_tokens") is not None:
            has_any_token_data = True
            total_tok += int(task_metrics.get("total_tokens") or 0)
            total_in_tok += int(task_metrics.get("input_tokens") or 0)
            total_out_tok += int(task_metrics.get("output_tokens") or 0)

        total_calls += int(task_metrics.get("inference_calls") or 0)
        cost_val = task_metrics.get("inference_cost_usd")
        if cost_val is not None:
            total_cost = (total_cost or 0.0) + float(cost_val)

    # Extended DDIV research metric aggregations
    failure_distribution: Dict[str, int] = {}
    critic_eval_count = 0
    critic_rej_count = 0
    mem_recovery_att = 0
    mem_recovery_succ = 0
    context_chars_list: List[int] = []
    agent_invoc_counts: Dict[str, int] = {}

    for r in records:
        data = r.model_dump() if hasattr(r, "model_dump") else dict(r)
        att_hist = data.get("attempt_history", [])
        for idx, att in enumerate(att_hist):
            # Failure distribution
            f_cat = att.get("failure_category")
            if f_cat:
                failure_distribution[f_cat] = failure_distribution.get(f_cat, 0) + 1
            fd_info = att.get("failure_detector") or {}
            g_cat = fd_info.get("granular_failure_type") or att.get("granular_failure_type")
            if g_cat:
                g_key = f"granular:{g_cat}"
                failure_distribution[g_key] = failure_distribution.get(g_key, 0) + 1

            # Patch Critic
            pc = att.get("patch_critic")
            if pc:
                critic_eval_count += 1
                if pc.get("approved") is False or pc.get("risk_level") == "HIGH":
                    critic_rej_count += 1

            # Memory retrieval in recovery attempts
            if is_full_ddiv and idx > 0:
                has_mem = bool(att.get("memory_retrieved") or att.get("memory_context"))
                if has_mem:
                    mem_recovery_att += 1
                    if att.get("internal_resolved", False):
                        mem_recovery_succ += 1

            # Context characters
            c_chars = att.get("context_characters")
            if c_chars is not None:
                context_chars_list.append(c_chars)
            elif att.get("source_files"):
                context_chars_list.append(len(att["source_files"]))

            # Agent invocations
            for invoc in att.get("model_invocations", []):
                ag = invoc.get("agent")
                if ag:
                    agent_invoc_counts[ag] = agent_invoc_counts.get(ag, 0) + 1

    tsr = resolved_count / total_tasks
    pass_at_1_rate = pass_at_1_count / total_tasks
    avg_attempts = sum(attempts_list) / total_tasks if attempts_list else 0.0
    mean_repair_time = sum(repair_times) / total_tasks if repair_times else 0.0
    med_repair_time = statistics.median(repair_times) if repair_times else 0.0

    repair_acc = (
        correct_patches_count / valid_patches_count
        if valid_patches_count > 0
        else None
    )

    regression_rate = (
        regression_count / valid_evaluated_count
        if valid_evaluated_count > 0
        else None
    )

    recovery_rate: Optional[float] = None
    if is_full_ddiv:
        if recovery_events_attempted > 0:
            recovery_rate = recovery_events_successful / recovery_events_attempted
        else:
            recovery_rate = None
    else:
        recovery_events_attempted = None
        recovery_events_successful = None
        recovery_rate = None

    cm_result = compute_confusion_matrix(diagnosis_samples) if is_full_ddiv else None

    # Compute extended rates
    recovery_gain = round(tsr - pass_at_1_rate, 4)
    critic_rej_rate = (
        round(critic_rej_count / critic_eval_count, 4)
        if critic_eval_count > 0
        else None
    )
    mem_retrieval_rate = (
        round(mem_recovery_att / recovery_events_attempted, 4)
        if (is_full_ddiv and recovery_events_attempted and recovery_events_attempted > 0)
        else None
    )
    mem_assisted_rec_rate = (
        round(mem_recovery_succ / mem_recovery_att, 4)
        if mem_recovery_att > 0
        else None
    )
    avg_ctx_chars = (
        round(sum(context_chars_list) / len(context_chars_list), 1)
        if context_chars_list
        else None
    )

    return ConditionAggregateMetrics(
        condition=condition_name,
        total_tasks=total_tasks,
        resolved_tasks=resolved_count,
        tsr=round(tsr, 4),
        pass_at_1_tasks=pass_at_1_count,
        pass_at_1_rate=round(pass_at_1_rate, 4),
        total_patches_generated=total_patches,
        invalid_or_empty_patches=invalid_or_empty_count,
        valid_patches_count=valid_patches_count,
        valid_incorrect_patches=valid_incorrect_count,
        correct_patches_count=correct_patches_count,
        repair_accuracy=round(repair_acc, 4) if repair_acc is not None else None,
        valid_evaluated_patches_count=valid_evaluated_count,
        regression_patches_count=regression_count,
        regression_rate=round(regression_rate, 4) if regression_rate is not None else None,
        recovery_events_attempted=recovery_events_attempted,
        recovery_events_successful=recovery_events_successful,
        recovery_success_rate=round(recovery_rate, 4) if recovery_rate is not None else None,
        recovery_gain=recovery_gain,
        repair_times=repair_times,
        mean_repair_time_seconds=round(mean_repair_time, 2),
        median_repair_time_seconds=round(med_repair_time, 2),
        average_attempts=round(avg_attempts, 2),
        total_input_tokens=total_in_tok if has_any_token_data else None,
        total_output_tokens=total_out_tok if has_any_token_data else None,
        total_tokens=total_tok if has_any_token_data else None,
        average_total_tokens=round(total_tok / total_tasks, 2) if has_any_token_data else None,
        total_inference_calls=total_calls,
        average_inference_calls=round(total_calls / total_tasks, 2),
        total_inference_cost_usd=round(total_cost, 4) if total_cost is not None else None,
        failure_detection=cm_result,
        failure_distribution=failure_distribution,
        patch_critic_rejection_rate=critic_rej_rate,
        memory_retrieval_rate=mem_retrieval_rate,
        memory_assisted_recovery_rate=mem_assisted_rec_rate,
        average_context_characters=avg_ctx_chars,
        agent_invocation_counts=agent_invoc_counts,
    )


def format_value(val: Any, is_pct: bool = False, decimal_places: int = 1) -> str:
    """Format numeric values or return N/A."""
    if val is None:
        return "N/A"
    if isinstance(val, (int, float)):
        if is_pct:
            return f"{val * 100:.{decimal_places}f}%"
        return f"{val:.{decimal_places}f}"
    return str(val)


def generate_summary_table(aggregates: Dict[str, ConditionAggregateMetrics]) -> str:
    """Produce a clear, standardized Markdown comparative summary table."""
    conditions = ["BASELINE", "RETRY_ONLY", "FULL_DDIV"]
    available_conds = [c for c in conditions if c in aggregates]
    if not available_conds:
        available_conds = list(aggregates.keys())

    headers = [
        "Metric",
        *(c for c in available_conds),
    ]

    def get_row(label: str, attr: str, is_pct: bool = False, decimals: int = 1) -> List[str]:
        row = [label]
        for c in available_conds:
            agg = aggregates[c]
            val = getattr(agg, attr, None)
            row.append(format_value(val, is_pct, decimals))
        return row

    def get_fd_row(label: str, attr: str) -> List[str]:
        row = [label]
        for c in available_conds:
            agg = aggregates[c]
            if agg.failure_detection:
                val = getattr(agg.failure_detection, attr, None)
                row.append(format_value(val, is_pct=True, decimal_places=1))
            else:
                row.append("N/A")
        return row

    rows = [
        get_row("Task Success Rate (TSR)", "tsr", is_pct=True),
        get_row("Pass@1", "pass_at_1_rate", is_pct=True),
        get_row("Recovery Gain (TSR - Pass@1)", "recovery_gain", is_pct=True),
        get_row("Repair Accuracy", "repair_accuracy", is_pct=True),
        get_row("Regression Rate", "regression_rate", is_pct=True),
        get_row("Recovery Success Rate", "recovery_success_rate", is_pct=True),
        get_fd_row("Failure Detection Precision", "macro_precision"),
        get_fd_row("Failure Detection Recall", "macro_recall"),
        get_fd_row("Failure Detection F1", "macro_f1"),
        get_row("Critic Rejection Rate", "patch_critic_rejection_rate", is_pct=True),
        get_row("Memory Retrieval Rate", "memory_retrieval_rate", is_pct=True),
        get_row("Avg Context Chars", "average_context_characters", is_pct=False, decimals=0),
        get_row("Mean Repair Time (s)", "mean_repair_time_seconds", is_pct=False, decimals=1),
        get_row("Median Repair Time (s)", "median_repair_time_seconds", is_pct=False, decimals=1),
        get_row("Average Attempts", "average_attempts", is_pct=False, decimals=2),
        get_row("Avg Tokens / Task", "average_total_tokens", is_pct=False, decimals=0),
        get_row("Avg Inference Calls", "average_inference_calls", is_pct=False, decimals=1),
        get_row("Total Inference Cost", "total_inference_cost_usd", is_pct=False),
    ]

    col_widths = [max(len(str(item)) for item in col) for col in zip(headers, *rows)]
    header_line = " | ".join(f"{h:<{w}}" for h, w in zip(headers, col_widths))
    sep_line = "-|-".join("-" * w for w in col_widths)

    out = [f"| {header_line} |", f"| {sep_line} |"]
    for r in rows:
        line = " | ".join(f"{item:<{w}}" for item, w in zip(r, col_widths))
        out.append(f"| {line} |")

    return "\n".join(out)

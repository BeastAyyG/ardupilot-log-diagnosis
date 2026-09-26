"""External baselines for the paper_eval leakage/benchmark study.

Step 4 of ``docs/PUBLICATION_PLAN.md`` requires two more baselines:

* **LogAnalyzer** — ArduPilot's own log-check tool. Its old path in the
  ArduPilot repository no longer exists (Step 4 confirms this), so this package
  ships a *static mapping* of the checks LogAnalyzer is known to perform to our
  label set. It is a translation layer, not a reimplementation; feed it a
  LogAnalyzer verdict dict and it returns the labels that verdict implies.
* **LLM** — an LLM reads the structured diagnosis report with a fixed prompt at
  temperature 0. It needs an API key (``ARDUPILOT_LLM_API_KEY``); without one it
  refuses to run rather than silently fabricating a number.

Both expose ``predict_label(report) -> str | None`` so ``paper_eval`` can score
them alongside the other methods. ``None`` means "no diagnosis" (abstention).
"""

from .loganalyzer_map import predict_label as loganalyzer_predict_label
from .llm_baseline import predict_label as llm_predict_label

__all__ = ["loganalyzer_predict_label", "llm_predict_label"]

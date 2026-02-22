import os
from .results import BenchmarkResults

class BenchmarkReporter:
    """Formats benchmark results for display."""
    
    def print_terminal(self, results: BenchmarkResults):
        metrics = results.compute_metrics()
        ov = metrics["overall"]
        
        print("╔═════════════════════════════════════════╗")
        print("║  ArduPilot Log Diagnosis Benchmark      ║")
        print("║  Engine: rules/ml hybrid v0.1.0         ║")
        print("╠═════════════════════════════════════════╣")
        print(f"║  Total logs:     {ov['total_logs']:<23}║")
        pct = (ov['successful_extractions'] / max(ov['total_logs'], 1)) * 100
        extracted_line = f"║  Extracted:      {ov['successful_extractions']} ({pct:.0f}%)"
        print(extracted_line + " " * max(1, 40 - len(extracted_line)) + "║")
        acc = ov['accuracy'] * 100
        acc_line = f"║  Overall acc:    {acc:.0f}%"
        print(acc_line + " " * max(1, 40 - len(acc_line)) + "║")
        f1_line = f"║  Macro F1:       {ov['macro_f1']:.2f}"
        print(f1_line + " " * max(1, 40 - len(f1_line)) + "║")
        print("╚═════════════════════════════════════════╝")
        
        print("\nPer-Label Results:")
        print("┌──────────────────────┬────┬────┬──────┬─────┐")
        print("│ Label                │ N  │ TP │ Prec │ F1  │")
        print("├──────────────────────┼────┼────┼──────┼─────┤")
        
        for label, vals in metrics["per_label"].items():
            if vals["support"] > 0 or vals["fp"] > 0:
                print(
                    f"│ {label[:20]:<20} │ {vals['support']:>2} │ {vals['tp']:>2} "
                    f"│ {vals['precision']:.2f} │ {vals['f1']:.2f} │"
                )
                
        print("└──────────────────────┴────┴────┴──────┴─────┘")
        
        print("\nMisclassification Analysis (top 5):")
        for conf in metrics["confusion_details"][:5]:
            print(f"  {conf['filename']}: truth={conf['ground_truth']} → pred={conf['predicted']}")
            
    def save_markdown(self, results: BenchmarkResults, path: str):
        with open(path, "w") as f:
            f.write(results.to_markdown())
            
    def save_json(self, results: BenchmarkResults, path: str):
        with open(path, "w") as f:
            f.write(results.to_json())

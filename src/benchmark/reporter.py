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
        print(f"║  Extracted:      {ov['successful_extractions']} ({pct:.0f}%)" + " "*(20-len(str(ov['successful_extractions']))-len(str(int(pct)))) + "║")
        acc = ov['accuracy'] * 100
        print(f"║  Overall acc:    {acc:.0f}%" + " "*(26-len(str(int(acc)))) + "║")
        print(f"║  Macro F1:       {ov['macro_f1']:.2f}" + " "*(23-len(f"{ov['macro_f1']:.2f}")) + "║")
        print("╚═════════════════════════════════════════╝")
        
        print("\nPer-Label Results:")
        print("┌──────────────────────┬────┬────┬──────┬─────┐")
        print("│ Label                │ N  │ TP │ Prec │ F1  │")
        print("├──────────────────────┼────┼────┼──────┼─────┤")
        
        for label, vals in metrics["per_label"].items():
            if vals["support"] > 0 or vals["fp"] > 0:
                print(f"│ {label[:20]:<20} │ {vals['support']:>2} │ {vals['tp']:>2} │ .{int(vals['precision']*100):02d}  │ .{int(vals['f1']*100):02d} │")
                
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

# Paper draft

`main.tex` is the manuscript, `references.bib` the bibliography, and
`figures/` holds figures generated from the committed result files.
`main.pdf` is the compiled draft.

## Rebuild

```bash
python paper/make_figures.py          # figures from data/benchmark/results/*.json
cd paper && pdflatex main && bibtex main && pdflatex main && pdflatex main
```

Overleaf also works: upload `main.tex`, `references.bib` and `figures/`.

## Before submitting

1. **Author block:** replace `AUTHOR NAME`, `AFFILIATION` and `EMAIL`.
2. **References:** verify every entry in `references.bib` against the
   publisher, and add the missing authors for RflyMAD and BASiC. The entries
   were written from memory.
3. **Human spot-check:** complete `data/benchmark/SPOT_CHECK.md` and add the
   agreement rate to Section 4. Without it, the paper must keep saying the
   labels are not human-reviewed.
4. **Numbers:** check them against `docs/EVIDENCE_LEDGER.md`, which cites
   `data/benchmark/results/paper_eval_v3.json` (commit `cd635e6`).
5. **Venue:** check the target journal's template and current quartile, then
   move the text into that template.
6. **Preprint:** post to arXiv and archive the dataset release on Zenodo for
   a DOI, then cite the DOI in Section 9.

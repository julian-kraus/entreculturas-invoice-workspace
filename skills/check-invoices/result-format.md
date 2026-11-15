# Draft format for `results.py save`

```json
{
  "type_id": "VOLUNTARIOS",
  "type_reason": "Signed request for a monthly volunteer bonus",
  "fields": {
    "total_amount": {"value": "30.000", "status": "found", "page": 1, "box": [0.7083, 0.4375, 0.8542, 0.4766]},
    "employee_name": {"value": "Relais Communautaire", "status": "uncertain", "page": 1, "box": [0.125, 0.1563, 0.4375, 0.1875],
                      "note": "Handwritten; may be a role, not a name"},
    "invoice_number": {"value": null, "status": "not_found"}
  },
  "visual": {
    "R_VOL_101": {"verdict": "pass", "reason": "AEXCID stamp shows file number, caption and percentage", "page": 1,
                  "box": [0.3542, 0.3438, 0.75, 0.4688]},
    "R_VOL_105": {"verdict": "unclear", "reason": "No receipt or bank proof on these pages"}
  },
  "questions": ["Is the proof of payment in a separate file?"],
  "summary": "Volunteer bonus of 30.000 XAF for August 2025. Stamp present; payment proof not found."
}
```

- Include every field of the chosen type. Use `"status": "not_found"` and `"value": null` when it is not on the document.
- `status`: `found`, `uncertain` or `not_found`.
- `verdict`: `pass`, `fail` or `unclear`. Judge only the rules listed in `visual_rules_to_judge` for this type.
- `box` and `page`: copy them from `grid.py finalize`. Leave both out if you could not confirm the location.
- `note` is optional, for anything a reviewer should know about one field.
- Keep `summary` to one or two plain sentences.

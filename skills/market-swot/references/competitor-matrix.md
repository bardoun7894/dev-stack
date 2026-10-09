# Competitor matrix

Columns: product | URL | target user | core loop/logic | key features | pricing | UI style | motion | onboarding | what they do better | what we do better.

competitors.json shape:
```json
{
  "generated": "YYYY-MM-DD",
  "subject": "project name",
  "competitors": [
    {
      "product": "", "url": "", "target_user": "", "core_loop": "",
      "key_features": [], "pricing": "", "ui_style": "", "motion": "",
      "onboarding": "", "better": "", "we_better": "",
      "sources": ["https://..."], "jev_score": 0
    }
  ]
}
```
Every non-empty field needs at least one URL in `sources`.

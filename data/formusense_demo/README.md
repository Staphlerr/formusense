# FormuSense Demo Dataset

This folder contains the working data for the 24-hour FormuSense lipstick shade prototype.

There are two dataset tracks in this folder:

1. **Prototype UI track** - small, hand-curated data for the actual clickable demo.
2. **Synthetic experiment track** - larger simulated data for charts, model-training mockups, and R&D storytelling.

Do not present any file in this folder as real consumer demand, real Paragon data, or production-ready formulation data.

## Track A - Prototype UI Data

Use these files for the main hackathon demo flow.

- `shade_catalog.csv`: 24 curated lipstick shade records for recommendation cards. IDs use the `SHD001` format.
- `demo_consumer_profiles.csv`: 12 simulated consumer profiles for profile fallback and segmentation.
- `demo_feedback.csv`: 30 simulated color-interest and wear-feedback records.
- `opportunities.csv`: R&D unmet demand opportunities for the dashboard.
- `base_formula_reference.csv`: non-production formula template used only to anchor the Formula Lab screen.
- `formula_draft_demo.csv`: AI-assisted draft example for the main demo opportunity.

Best use:

- Consumer UI recommendation cards.
- Feedback form demo.
- R&D dashboard cards.
- Formula Lab screen.

## Track B - Synthetic Experiment Data

Use these files for charts, model-training explanation, and backup analysis screens.

- `shade_data.csv`: 500 synthetic lipstick shades with CIELAB/HSV-like color descriptors. IDs use the `S001` format.
- `hedonic_data.csv`: 5,000 synthetic hedonic observations from 100 simulated consumers x 50 sampled shades.
- `shade_preference_summary.csv`: aggregated mean/median liking by shade.
- `model_training_table.csv`: hedonic data joined to shade color descriptors.
- `formulation_data.csv`: 200 synthetic candidate lipstick formulations normalized to 100%.
- `formula_outputs.csv`: synthetic predicted color/performance outputs for candidate formulations.

Best use:

- Preference distribution charts.
- "Community preference" visualization.
- Explaining how a future ML model could be trained.
- R&D dashboard mock analytics.

## Important ID Note

The two tracks are not directly linked yet:

- Prototype UI uses `SHD001`, `SHD002`, etc.
- Synthetic experiment data uses `S001`, `S002`, etc.
- Synthetic formula data uses `F001`, `F002`, etc.

Do not join `SHD` records with `S` records unless a mapping table is created.

For the 24-hour demo, use Track A as the primary product data. Use Track B only as supporting analytics or visualization data.

## AI and Model Training Note

No custom model training is required for the hackathon.

Recommended implementation:

- Use AI API for photo/profile estimation when available.
- Use rule-based matching for shade recommendation.
- Use AI API for personal notes, R&D summaries, and formula rationale.
- Use synthetic data only to demonstrate what future training data could look like.

## Pitch-Safe Statement

"This prototype uses curated demo data, synthetic preference data, and AI API calls to demonstrate the closed-loop flow. Consumer photo analysis and formula draft generation are assistive. Final formulation decisions still require formulator review and laboratory validation."

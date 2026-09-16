Lipstick AI Hackathon Synthetic Dataset
==========================================

Files:
1. shade_data.csv
   500 synthetic lipstick shades with synthetic CIELAB/HSV-like color descriptors.
   image_file values are placeholders for prototype images.

2. hedonic_data.csv
   100 synthetic consumers x 50 sampled shades = 5,000 synthetic observations.
   hedonic_score uses a 1-9 scale.
   IMPORTANT: These are synthetic data, NOT real consumer responses.

3. formulation_data.csv
   200 synthetic candidate lipstick formulations. Percentages are normalized to 100%.
   IMPORTANT: These are synthetic candidate formulas, NOT validated manufacturing formulas.

4. formula_outputs.csv
   Synthetic predicted color/performance outputs for the candidate formulas.

5. shade_preference_summary.csv
   Aggregated mean/median liking by shade.

6. model_training_table.csv
   Hedonic data joined to shade color descriptors.

Suggested hackathon pipeline:
reference image -> computer vision -> CIELAB -> preference model -> target shade ->
formulation optimizer -> candidate formula.

Do not present synthetic data as experimental/consumer-study results.

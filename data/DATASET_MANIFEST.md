# FormuSense Dataset Manifest

This folder collects the datasets and source references for the 24-hour FormuSense lipstick shade hackathon prototype.

## Five team CSVs now used in the app

These files sit directly under `data/`. The team has **no PT Paragon dataset**; these are team-supplied demo files, not Paragon portfolio, consumer, or laboratory records. Treat their values as demo data unless a separate provenance and validation record is supplied.

| File | Rows | Current use |
| --- | ---: | --- |
| `ALL DATASET - Shade Catalog.csv` | 30 | Main recommendation pool, brand/shade/hex/finish labels. All 30 are treated as available **within this demo catalog**, not confirmed Paragon SKUs. |
| `ALL DATASET - Hedonic Customer Data.csv` | 600 | Synthetic 1–9 liking signal by shade and approximate skin-tone/undertone cohort; small score bonus and consumer spectrum. Joined to the 30-shade catalog by exact shade name. |
| `ALL DATASET - Feedback.csv` | 300 | Historical-style demo appeal and rating/issue summary; joined by shade ID. Actual product wear is not verified by this file. New consented app feedback stays in SQLite and is counted separately. |
| `ALL DATASET - Base Formula.csv` | 500 | Reference compositions for a nearest-three, weighted draft in Formula Lab. Ingredient-group percentages sum to about 100%, but there are no measured stability/safety/performance outcomes. |
| `ALL DATASET - Gap Comparison.csv` | 100 | Candidate gaps and target descriptions on the R&D page. Only 9 rows match both existing shade name and brand in the 30-shade demo catalog. An unmatched row is **not** evidence that Paragon lacks a product. |

The formula and gap files are not joined to the 30-shade catalog by ID. Formula drafts are generated from stated gap attributes (family, finish, target L*, pigment, wax) and the nearest base-formula rows; they are exploratory directions requiring formulator review and lab tests. Finish demand is also compared directly against the 30-shade catalog using preferences in the 600-row hedonic file and new local feedback.

## Face data status

`data/asian face/` now contains 99 JPG face photos plus the 2-byte placeholder file `face`. The photos have no accompanying per-image reference labels or source/usage documentation, so this is **not yet a ground-truth dataset** for skin tone, undertone, or lip pigmentation and is not used to score or tune those classifiers. A file-size/dimension audit found 36 photos with a side shorter than the local analyzer's 240-pixel minimum, and one exact duplicate pair (`img227.jpg`, `img243.jpg`). The remaining images may be useful as exploratory face/lip detection inputs after their source and usage permissions are checked; their mere presence does not establish expected color labels.

To evaluate `services/local_vision.py`, each usable photo needs an independently assigned reference label (for example, `image_file`, `skin_tone` or Monk Skin Tone index, `undertone`, optional `lip_pigmentation`, and how each label was assigned). The image alone can test whether face and lip landmarks are detected, but cannot establish the correct undertone or pigmentation. Keep the image source, usage permission, and lighting/annotation notes with the labels; do not turn the pipeline's own predictions into its ground truth.

## Synthetic tone pseudo-label set

`data/pseudo-labels-tone/` contains 30 synthetic 512×512 portraits, `annotations.csv`, an XLSX copy, and a source/limitations README. All 30 CSV image paths exist. The set is balanced across six source skin-tone categories (five each: `fair`, `light`, `medium`, `tan`, `dark`, `deep`); the current app instead uses five categories (`light`, `light_medium`, `medium`, `tan`, `deep`), so a documented mapping would be needed before comparing labels.

The `skin_tone` and `undertone` fields were copied from the [Fashion Stylist Multimodal Dataset](https://huggingface.co/datasets/lihicarmeli/fashion-stylist-multimodal) metadata. Its portraits were generated with SDXL, and its image prompt does **not** explicitly include undertone. Therefore the source undertone field is not a trustworthy visual target for the rendered image. `pigmentasi_bibir` and `catatan` are model-assisted visual pseudo-labels, often affected by apparent makeup or stylization; they are not measurements of natural lip pigmentation. The CSV marks 21 rows `usable`, five `small_face`, two `stylized`, one `limited_color`, and one `image_artifact`, but these flags do not establish clinical or colorimetric validity.

This folder is **not used by the consumer recommendation flow or as ground truth**. Run `python manage.py audit_pseudo_labels` to pass its 30 images through the local photo analyzer and create `output/pseudo_label_smoke_test.csv` for side-by-side review. The report records source metadata/pseudo-labels and app estimates in separate columns, including analysis failures and measured Lab values when available. It does not calculate an accuracy score, train a model, or validate performance on real consumer photos. Keep model predictions and pseudo-labels separate from independently annotated evaluation labels.

## What Is Ready to Use

### 1. Demo Dataset - Main Prototype Data

Folder: `data/formusense_demo/`

Legacy supporting demo data for the old opportunity cards and supplementary charts. The consumer recommendation pool now comes from the five team CSVs above.

Files:

- `shade_catalog.csv` - 24 lipstick shade records for recommendation cards.
- `demo_consumer_profiles.csv` - 12 simulated consumer profiles for segmentation and fallback.
- `demo_feedback.csv` - 30 simulated feedback records.
- `opportunities.csv` - R&D unmet demand opportunities.
- `base_formula_reference.csv` - non-production base formula template.
- `formula_draft_demo.csv` - AI-assisted formula draft example.
- `shade_data.csv` - 500 synthetic lipstick shade records using `S001` IDs.
- `hedonic_data.csv` - 5,000 synthetic hedonic observations.
- `shade_preference_summary.csv` - aggregated synthetic preference summary.
- `model_training_table.csv` - synthetic hedonic data joined to color descriptors.
- `formulation_data.csv` - 200 synthetic candidate formulas using `F001` IDs.
- `formula_outputs.csv` - synthetic predicted outputs for candidate formulas.

Status: ready for hackathon demo.

Important label: `demo_simulation` or `demo_template`. Do not present this as real market data.

Important ID note: the curated UI files use `SHD001` IDs, while the larger synthetic shade files use `S001` IDs. Do not join those tracks unless a mapping table is created.

### 2. The Pudding Makeup Shades Dataset

Folder: `data/external_sources/the_pudding_makeup_shades/`

Source:

- GitHub: https://github.com/the-pudding/data/tree/master/makeup-shades
- Raw CSV: https://raw.githubusercontent.com/the-pudding/data/refs/heads/master/makeup-shades/shades.csv

Files downloaded:

- `shades.csv`
- `README.md`

Use for:

- Understanding how makeup shade datasets store color values.
- Reference for `hex`, `H`, `S`, `V`, and `L` color columns.
- Optional foundation shade visual comparison.

Do not use for:

- Lipstick recommendation directly.
- Hedonic review.
- Consumer undertone labels.

Reason: this is a foundation shade dataset, not lipstick shade preference data.

### 3. Nature / Figshare Liquid Formulations Dataset

Folder: `data/external_sources/nature_shampoo_formulation/`

Sources:

- Nature article: https://www.nature.com/articles/s41597-024-03573-w
- Figshare collection: https://doi.org/10.6084/m9.figshare.c.7132624.v1
- GitHub code: https://github.com/sustainable-processes/formulations-prep

Files downloaded:

- `LiquidFormulationsDataset_2023.json`
- `BASF Surfactants Information.csv`
- `BASF Formulation Ingredient Structures.pptx`
- `SpeciesDictionary.csv`
- `formulations_prep_README.md`
- Figshare metadata JSON files.

Not downloaded:

- `formulation-images.zip` from Figshare, because it is about 358 MB and contains shampoo formulation stability images. Direct URL is stored in `figshare_article_25451869.json`.

Use for:

- Scientific reference that formulation ML datasets can connect composition with stability, turbidity, viscosity, and rheology.
- R&D dashboard credibility.
- Explaining why lab validation is needed.

Do not use for:

- Lipstick shade recommendation.
- Lipstick pigment formula finalization.
- Consumer hedonic preference.

Reason: this is a shampoo/liquid formulation dataset, not a lipstick dataset.

### 4. Capstone Colors Product/Swatch Dataset

Folder: `data/external_sources/capstone_colors_original/`

Source:

- GitHub folder: https://github.com/ConstanzaSchibber/capstone_colors/tree/main/data/img/original
- Parent repository: https://github.com/ConstanzaSchibber/capstone_colors

Files downloaded:

- `github_api_original_listing.json` - listing for 516 original image/document files.
- `source_data_README.md` - source README for the data folder.
- `product_metadata/mauve_products.csv` - 560 mauve product metadata rows.
- `product_metadata/peach_products.csv` - 598 peach product metadata rows.
- `processed/products_app.csv` - 506 processed app rows with product, shade, image URL, CIELAB-related fields, LLM fields, and color grouping.
- `processed/metadata.csv` - small metadata table.
- `processed/README.md` - source processed-folder README.

Not downloaded:

- All 516 original image files. The source folder is about 100.9 MB and contains mixed image/document file types. The listing is stored locally so selected images can be downloaded later if needed.

Use for:

- Supporting lipstick/blush shade metadata.
- Swatch/product image references.
- Color descriptor examples such as mauve/peach, finish, intensity, and undertone-related labels.
- Optional color extraction or CIELAB demonstration.

Do not use for:

- Proving consumer preference.
- Proving shade suitability for a specific undertone.
- Training a production vision model during the 24-hour hackathon.

Reason: this is useful product and color metadata, but it is not validated consumer preference data and not a clinical/hedonic study.

## Sources Mentioned by the Team That Need Manual Download

These are usable as supporting sources, but they are hosted on Kaggle or external pages that require login/manual download.

### 5. Kaggle Makeup or No Makeup

Source: https://www.kaggle.com/code/kerneler/starter-makeup-or-no-makeup-6e87f9f8-a/input

Use for:

- Sample face photos for UI demo.
- Optional visual placeholders.

Do not use for:

- Training undertone detection.
- Claiming lipstick shade suitability.

Reason: this is makeup/no-makeup image data, not undertone-lipstick preference data.

Manual action:

1. Open the Kaggle link while logged in.
2. Download the input dataset from the notebook page.
3. Put files under `data/external_sources/kaggle_makeup_or_no_makeup/`.

### 6. Kaggle Makeup Analysis / Shade Input

Source: https://www.kaggle.com/code/risakashiwabara/makeup-analysis-pie-chart-value-count-data/input

Use for:

- Exploratory shade/product distribution if the input files are available.
- Reference only.

Do not use as the main lipstick recommendation dataset unless it has lipstick shade names, color values, and usable labels after inspection.

Manual action:

1. Open the Kaggle link while logged in.
2. Download the input files.
3. Put files under `data/external_sources/kaggle_makeup_analysis/`.

### 7. Kaggle Sephora Products and Skincare Reviews

Source: https://www.kaggle.com/datasets/nadyinky/sephora-products-and-skincare-reviews

Use for:

- Review/rating schema inspiration.
- Sentiment text examples if allowed by Kaggle license.

Do not use for:

- Lipstick shade matching.
- Hedonic lipstick claims.

Reason: this is skincare/product review data, not lipstick shade preference by undertone.

Manual action:

1. Open the Kaggle dataset while logged in.
2. Download the dataset.
3. Put files under `data/external_sources/kaggle_sephora_reviews/`.

### 8. Handbook of Pharmaceutical Excipients PDF

Source provided by team: https://adiyugatama.wordpress.com/wp-content/uploads/2012/03/handbook-of-pharmaceutical-excipients-6th-ed.pdf

Use for:

- Excipient reference reading by the pharmacy/formulation team.
- Ingredient function vocabulary.

Do not use for:

- Automatic formula generation without human review.
- Copying large text into the product or pitch.

Reason: it is a reference book, not a structured dataset.

### 9. IQONIC AI Lip Analysis

Source: https://www.iqonicai.com/ai-lip-analysis

Use for:

- Benchmarking the consumer-facing lip analysis experience.

Do not use for:

- Dataset extraction.
- Training data.

Reason: it is a benchmark/product page, not a downloadable dataset.

## Recommendation for the Hackathon

Use this combination:

1. The five `ALL DATASET - *.csv` files as the current consumer catalog/evidence and R&D gap/formula demo track, with unverified provenance labelled.
2. `data/formusense_demo/` as the legacy opportunity and supplementary synthetic chart track.
3. The Pudding dataset only as color/shade reference.
4. Nature/Figshare formulation dataset only as R&D/scientific reference.
5. Capstone Colors as supporting swatch/product metadata.
6. Kaggle datasets only if the team can download them manually in time.

No custom AI model training is needed for the 24-hour hackathon. Use AI API + rule-based recommendation + demo data + manual fallback.

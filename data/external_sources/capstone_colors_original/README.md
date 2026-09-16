# Capstone Colors External Source

Source folder provided by the team:

https://github.com/ConstanzaSchibber/capstone_colors/tree/main/data/img/original

This local folder stores the useful metadata and listings from that repository.

## Downloaded

- `github_api_original_listing.json`: GitHub API listing for the original image folder.
- `github_api_data_listing.json`: GitHub API listing for the source `data/` folder.
- `github_api_product_metadata_listing.json`: GitHub API listing for `data/product_metadata/`.
- `github_api_processed_listing.json`: GitHub API listing for `data/processed/`.
- `source_data_README.md`: source README.
- `product_metadata/mauve_products.csv`: product metadata for mauve-related products.
- `product_metadata/peach_products.csv`: product metadata for peach-related products.
- `processed/products_app.csv`: processed product/shade/color table used by the source app.
- `processed/metadata.csv`: small source metadata file.
- `processed/README.md`: source processed-folder README.

## Not Downloaded

The full `data/img/original` folder contains 516 files and is about 100.9 MB. It also includes mixed file types, not only clean swatch images. Download selected image files only if the UI needs specific visuals.

## Recommended Use

Use this source as supporting swatch/product metadata for color and shade examples. Do not present it as consumer preference data or as proof that a shade suits a specific undertone.

For the 24-hour hackathon, this source is best used as:

- reference product/shade metadata,
- optional swatch image source,
- color descriptor inspiration,
- support for visualizing CIELAB/color extraction.

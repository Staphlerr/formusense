FormuSense — Synthetic Lip Pseudo-Reference Set (30 samples)

SOURCE
Hugging Face: lihicarmeli/fashion-stylist-multimodal
https://huggingface.co/datasets/lihicarmeli/fashion-stylist-multimodal

CONTENTS
- 30 selected synthetic portraits, balanced to 5 samples per source skin_tone:
  fair, light, medium, tan, dark, deep.
- skin_tone and undertone are copied from the source dataset metadata.
- pigmentasi_bibir and catatan are model-assisted visual pseudo-labels added for
  FormuSense prototype development.
- confidence describes confidence in the added lip pseudo-label, not confidence
  in the source skin_tone/undertone metadata.
- uncertain is used when the lip area is too small, unclear, or affected by an
  image artifact.

IMPORTANT LIMITATIONS
1. These portraits are synthetic SDXL images, not photographs of real participants.
2. Added lip labels are PSEUDO-LABELS, not clinical, dermatological, or colorimetric ground truth.
3. The source dataset's undertone is structured metadata and was not explicitly
   included in the SDXL portrait-generation prompt.
4. Several synthetic portraits may contain makeup, stylization, or generation artifacts.
5. Do not use this set to claim validated accuracy on real-world natural lip pigmentation.

PIGMENTATION LABELS
- low: visually low/dilute pigmentation or very light nude appearance
- medium: moderate visible pigmentation/contrast
- medium_high: clearly stronger pigmentation/contrast
- high: very strong/dark/saturated visible lip color
- uncertain: insufficient visual evidence

Recommended wording in a report:
"We augmented a public synthetic multimodal dataset with model-assisted visual
lip-pigmentation pseudo-labels for prototype development. These annotations are
not treated as real-world ground truth."

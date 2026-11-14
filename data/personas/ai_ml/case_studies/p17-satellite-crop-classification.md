# Satellite crop classification

In 2021, I worked with a client in agritech (name withheld) on a satellite-based crop classification problem. The goal was to turn Sentinel-2 imagery into reliable parcel-level labels for six crop types. The core challenge was not just building a classifier, but handling the image-to-field workflow end to end: reading multi-band raster data, aligning it with parcel boundaries, and training a model that could distinguish visually similar crops from remote sensing signals.

I built the solution in Python with PyTorch, using `rasterio` to load and prepare the satellite tiles and a U-Net segmentation model to predict crop classes across field parcels. Rather than treating the task as simple image classification, I framed it as segmentation so the model could learn spatial structure within and around parcel shapes. That let me map predictions back to the field level in a way that was more useful for agronomic decision-making.

A key part of the work was preparing the training pipeline so it could ingest raster bands consistently and support experimentation. I focused on band handling, normalization, tiling, and mask alignment, since these steps strongly affect performance when working with Sentinel-2 imagery. From there, I iterated on the U-Net training setup and evaluation, measuring quality with mean IoU across the six crop classes.

Example of the kind of preprocessing setup I used:

```python
import rasterio

with rasterio.open("sentinel2_tile.tif") as src:
    image = src.read([2, 3, 4, 8])  # selected bands
    profile = src.profile

image = image.astype("float32") / 10000.0
image = image.transpose(1, 2, 0)
```

The final model reached a mean IoU of 0.74 across the six crop classes. For this kind of remote sensing task, that result reflected a solid balance between parcel-level detail and class separation. The project showed how a segmentation-first approach can be effective when the input is multi-band satellite imagery and the output needs to align with agricultural field boundaries.

# Ceramic tile defect detection

At **Halvorsen Ceramics**, I built a camera-based inspection system to detect cracks and chips on ceramic tiles as they moved along the kiln line. The goal was to catch defects early without slowing production or creating too many unnecessary rejects. I worked on this as a fixed engagement from **2022-05 to 2022-08**.

The core challenge was making computer vision reliable enough for an industrial environment. Tiles needed to be inspected in motion, with consistent detection performance and a deployment path that could run directly on an industrial PC beside the line. I designed the system around **Python**, **PyTorch**, **YOLOv8**, and **OpenCV**, focusing on a workflow that could take camera input, process frames efficiently, and flag defect regions with low latency.

My approach started with a detector tuned specifically for the two defect classes that mattered most: cracks and chips. I used OpenCV for the image pipeline and PyTorch for training and experimentation, then prepared the model for export so it could run outside the training environment. To make the deployment practical on the factory floor, I optimized the network for a lighter runtime footprint before exporting it to **ONNX**. That allowed the final application to run on the industrial PC near the kiln line rather than relying on a more complex server setup.

A simple representation of the export path looked like this:

```python
import torch

model.eval()
example = torch.randn(1, 3, 640, 640)

with torch.no_grad():
    torch.onnx.export(
        model,
        example,
        "ceramic_defect_detector.onnx",
        opset_version=12,
        input_names=["images"],
        output_names=["detections"]
    )
```

The result was a production-ready detector that identified cracks with **97.4% recall** and reduced **false rejects from 8% to 2.1%**. Just as importantly, it fit into the factory workflow as a camera-based system running beside the kiln line, which made it easier for Halvorsen Ceramics to apply automated inspection without disrupting operations.

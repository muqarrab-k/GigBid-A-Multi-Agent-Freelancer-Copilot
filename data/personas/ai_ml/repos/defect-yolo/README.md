# defect-yolo

Camera-based ceramic tile defect detection for cracks and chips. Fine-tunes YOLOv8 on tile images and exports the detector to ONNX for use on an industrial PC beside the kiln line.

## Setup

Install the Python stack used by the training and export scripts:

- Python
- PyTorch
- YOLOv8
- OpenCV
- ONNX

Prepare a dataset of tile images with crack and chip labels in the format expected by `train.py`.

## Usage

```bash
# fine-tune YOLOv8 on labeled tile images
python train.py

# export the trained detector to ONNX with int8 quantisation
python export_onnx.py
```

`train.py` handles YOLOv8 fine-tuning on crack and chip annotations.  
`export_onnx.py` exports the trained network to ONNX and runs a quick accuracy check.

## Notes

- The repository is focused on deployment to an industrial camera setup.
- The export path uses int8 quantisation before ONNX output.
- The detector was built to reduce missed cracks and cut down false rejects in production.
- The codebase reflects work completed in a fixed engagement during 2022.

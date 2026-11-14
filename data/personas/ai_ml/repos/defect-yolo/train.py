import argparse
from pathlib import Path

import torch
from ultralytics import YOLO
from ultralytics.data.utils import autosplit
from ultralytics.utils.checks import check_yaml


def parse_args():
    parser = argparse.ArgumentParser(description="Fine-tune YOLOv8 for tile crack and chip detection.")
    parser.add_argument("--data", type=str, default="data/dataset.yaml", help="Path to dataset YAML")
    parser.add_argument("--model", type=str, default="yolov8n.pt", help="Base YOLOv8 checkpoint")
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", type=str, default="0" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--project", type=str, default="runs/defect-yolo")
    parser.add_argument("--name", type=str, default="tile_defect_finetune")
    return parser.parse_args()


def prepare_dataset(data_yaml: str):
    data_path = Path(data_yaml)
    if not data_path.exists():
        raise FileNotFoundError(f"Dataset YAML not found: {data_yaml}")

    # Ensure the dataset config can be parsed by Ultralytics.
    check_yaml(str(data_path))

    # Optional auto-split for image folders used in local experiments.
    img_root = data_path.parent / "images"
    if img_root.exists():
        autosplit(str(img_root), weights=(0.8, 0.1, 0.1), annotated=True)


def main():
    args = parse_args()
    prepare_dataset(args.data)

    model = YOLO(args.model)
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        project=args.project,
        name=args.name,
        pretrained=True,
        patience=20,
        workers=4,
        exist_ok=True,
    )

    # Export a deployment-ready ONNX model for the industrial PC.
    best_ckpt = Path(args.project) / args.name / "weights" / "best.pt"
    if best_ckpt.exists():
        trained = YOLO(str(best_ckpt))
        trained.export(format="onnx", opset=12, dynamic=False)


if __name__ == "__main__":
    main()

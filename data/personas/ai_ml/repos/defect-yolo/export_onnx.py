from pathlib import Path
import argparse
import cv2
import numpy as np
import torch

try:
    from ultralytics import YOLO
except ImportError as exc:
    raise SystemExit("ultralytics is required to export the YOLOv8 model") from exc


def load_image(image_path: str, size: int = 640) -> torch.Tensor:
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = cv2.resize(img, (size, size), interpolation=cv2.INTER_LINEAR)
    img = img.astype(np.float32) / 255.0
    img = np.transpose(img, (2, 0, 1))
    return torch.from_numpy(img).unsqueeze(0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", default="weights/best.pt")
    parser.add_argument("--image", default="data/sample.jpg")
    parser.add_argument("--out", default="exports/crack_chip.onnx")
    parser.add_argument("--imgsz", type=int, default=640)
    args = parser.parse_args()

    model = YOLO(args.weights)
    export_path = model.export(format="onnx", imgsz=args.imgsz, simplify=True, dynamic=False)
    export_path = Path(export_path)
    target_path = Path(args.out)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if export_path != target_path:
        target_path.write_bytes(export_path.read_bytes())

    img = load_image(args.image, args.imgsz)
    torch_out = model.predict(args.image, imgsz=args.imgsz, verbose=False)

    onnx_model = cv2.dnn.readNetFromONNX(str(target_path))
    blob = img.numpy()
    onnx_model.setInput(blob)
    _ = onnx_model.forward()

    print(f"Exported: {target_path}")
    print(f"Quick check detections: {len(torch_out[0].boxes) if torch_out else 0}")


if __name__ == "__main__":
    main()

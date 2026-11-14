Serverless image pipeline for S3 uploads: generate watermarked web sizes and serve them through CloudFront.

## Setup

- Node.js
- AWS Lambda
- AWS S3
- Sharp
- CloudFront

Install dependencies and deploy the Lambda functions in your AWS environment. The repo includes:
- `handler.ts` for S3 upload events
- `resize.ts` for Sharp resize and watermark processing

## Usage

Upload an image to the source S3 bucket. The upload triggers the Lambda handler, which calls the resize flow to produce three web sizes with a watermark. The outputs are then available behind the CDN.

```bash
# upload a source image to the configured S3 bucket
aws s3 cp ./input.jpg s3://YOUR_BUCKET/uploads/input.jpg

# Lambda runs on upload and writes processed variants
# serve the generated assets through CloudFront
```

## Notes

Built for a fixed engagement in mid-2024. The pipeline processed millions of images and reduced hosting spend significantly. The code is split into a thin upload handler and a Sharp-based transform module to keep the path simple and easy to reason about.

import { S3Event, S3Handler } from "aws-lambda";
import { GetObjectCommand, PutObjectCommand, S3Client } from "@aws-sdk/client-s3";
import sharp from "sharp";

const s3 = new S3Client({});

const bucket = process.env.OUTPUT_BUCKET || "";
const watermarkText = process.env.WATERMARK_TEXT || "img-pipeline";

const sizes = [
  { suffix: "sm", width: 480 },
  { suffix: "md", width: 960 },
  { suffix: "lg", width: 1440 },
];

function outputKey(key: string, suffix: string) {
  const dot = key.lastIndexOf(".");
  const base = dot >= 0 ? key.slice(0, dot) : key;
  return `${base}-${suffix}.jpg`;
}

function watermarkSvg(text: string) {
  return Buffer.from(`
    <svg width="400" height="80" xmlns="http://www.w3.org/2000/svg">
      <rect width="100%" height="100%" fill="transparent"/>
      <text x="20" y="50" font-family="Arial, sans-serif" font-size="28" fill="white" opacity="0.7">${text}</text>
    </svg>
  `);
}

export const handler: S3Handler = async (event: S3Event) => {
  const records = event.Records || [];
  for (const record of records) {
    const sourceBucket = record.s3.bucket.name;
    const key = decodeURIComponent(record.s3.object.key.replace(/\+/g, " "));

    const response = await s3.send(new GetObjectCommand({ Bucket: sourceBucket, Key: key }));
    const body = response.Body as any;
    const input = await body.transformToByteArray();

    for (const size of sizes) {
      // Resize and watermark each web variant
      const image = sharp(Buffer.from(input))
        .resize({ width: size.width, withoutEnlargement: true })
        .jpeg({ quality: 82 })
        .composite([{ input: watermarkSvg(watermarkText), gravity: "southeast" }]);

      const output = await image.toBuffer();
      await s3.send(
        new PutObjectCommand({
          Bucket: bucket,
          Key: outputKey(key, size.suffix),
          Body: output,
          ContentType: "image/jpeg",
          CacheControl: "public, max-age=31536000, immutable",
        })
      );
    }
  }
};

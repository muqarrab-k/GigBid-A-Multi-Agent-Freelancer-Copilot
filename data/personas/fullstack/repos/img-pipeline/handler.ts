import type { S3Event, S3Handler } from "aws-lambda";
import { S3Client, GetObjectCommand, PutObjectCommand } from "@aws-sdk/client-s3";
import sharp from "sharp";

const s3 = new S3Client({});

const BUCKET = process.env.OUTPUT_BUCKET || "";
const WATERMARK_TEXT = process.env.WATERMARK_TEXT || "img-pipeline";

const streamToBuffer = async (stream: any): Promise<Buffer> => {
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  return Buffer.concat(chunks);
};

export const handler: S3Handler = async (event: S3Event) => {
  for (const record of event.Records) {
    const bucket = record.s3.bucket.name;
    const key = decodeURIComponent(record.s3.object.key.replace(/\+/g, " "));

    if (!BUCKET) throw new Error("OUTPUT_BUCKET is not set");

    const input = await s3.send(new GetObjectCommand({ Bucket: bucket, Key: key }));
    const body = await streamToBuffer(input.Body as any);

    const base = sharp(body).rotate();
    const small = await base.clone().resize(640).jpeg({ quality: 82 }).toBuffer();
    const medium = await base.clone().resize(1280).jpeg({ quality: 85 }).toBuffer();

    const meta = await base.metadata();
    const watermark = Buffer.from(
      `<svg width="${meta.width || 1200}" height="${meta.height || 800}">
        <text x="24" y="${(meta.height || 800) - 24}" font-size="28" fill="white" opacity="0.7">${WATERMARK_TEXT}</text>
      </svg>`
    );

    const watermarked = await base
      .clone()
      .composite([{ input: watermark, gravity: "southwest" }])
      .jpeg({ quality: 85 })
      .toBuffer();

    const prefix = key.replace(/\.[^.]+$/, "");
    await Promise.all([
      s3.send(new PutObjectCommand({ Bucket: BUCKET, Key: `${prefix}-sm.jpg`, Body: small, ContentType: "image/jpeg" })),
      s3.send(new PutObjectCommand({ Bucket: BUCKET, Key: `${prefix}-md.jpg`, Body: medium, ContentType: "image/jpeg" })),
      s3.send(new PutObjectCommand({ Bucket: BUCKET, Key: `${prefix}-wm.jpg`, Body: watermarked, ContentType: "image/jpeg" })),
    ]);
  }
};

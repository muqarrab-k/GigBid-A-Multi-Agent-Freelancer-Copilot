import { Worker, Job } from 'bullmq';
import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3';
import puppeteer from 'puppeteer';

type StatementJob = {
  statementId: string;
  ownerId: string;
  html: string;
  bucket: string;
  keyPrefix?: string;
};

const connection = {
  host: process.env.REDIS_HOST ?? '127.0.0.1',
  port: Number(process.env.REDIS_PORT ?? 6379),
};

const s3 = new S3Client({ region: process.env.AWS_REGION ?? 'us-east-1' });

async function renderPdf(html: string): Promise<Buffer> {
  const browser = await puppeteer.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await page.setContent(html, { waitUntil: 'networkidle0' });
    return await page.pdf({ format: 'A4', printBackground: true });
  } finally {
    await browser.close();
  }
}

async function uploadPdf(bucket: string, key: string, body: Buffer) {
  await s3.send(
    new PutObjectCommand({
      Bucket: bucket,
      Key: key,
      Body: body,
      ContentType: 'application/pdf',
    })
  );
}

export const statementWorker = new Worker<StatementJob>(
  'owner-statements',
  async (job: Job<StatementJob>) => {
    const { statementId, ownerId, html, bucket, keyPrefix = 'statements' } = job.data;

    // Render the statement to PDF
    const pdf = await renderPdf(html);

    const key = `${keyPrefix}/${ownerId}/${statementId}.pdf`;
    // Store the PDF in S3 for later retrieval
    await uploadPdf(bucket, key, pdf);

    return { bucket, key };
  },
  {
    connection,
    concurrency: 2,
    attempts: 3,
    removeOnComplete: true,
    removeOnFail: false,
  }
);

statementWorker.on('failed', (job, err) => {
  if (job) {
    console.error(`Statement job failed: ${job.id}`, err);
  }
});

export default statementWorker;

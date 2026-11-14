import puppeteer, { Browser, PDFOptions } from 'puppeteer';

type RenderOptions = {
  html: string;
  format?: PDFOptions['format'];
  margin?: PDFOptions['margin'];
  printBackground?: boolean;
};

let browserPromise: Promise<Browser> | null = null;

async function getBrowser(): Promise<Browser> {
  if (!browserPromise) {
    browserPromise = puppeteer.launch({
      headless: 'new',
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    });
  }

  return browserPromise;
}

export async function renderHtmlToPdfBuffer(options: RenderOptions): Promise<Buffer> {
  const browser = await getBrowser();
  const page = await browser.newPage();

  try {
    await page.setViewport({ width: 1280, height: 1800, deviceScaleFactor: 1 });
    await page.setContent(options.html, { waitUntil: 'networkidle0' });

    const pdf = await page.pdf({
      format: options.format ?? 'Letter',
      margin: options.margin ?? { top: '24px', right: '24px', bottom: '24px', left: '24px' },
      printBackground: options.printBackground ?? true,
    });

    return Buffer.isBuffer(pdf) ? pdf : Buffer.from(pdf);
  } finally {
    // Always close the page to keep the worker stable.
    await page.close().catch(() => undefined);
  }
}

export async function closeBrowser(): Promise<void> {
  if (!browserPromise) return;

  const browser = await browserPromise;
  browserPromise = null;
  await browser.close().catch(() => undefined);
}

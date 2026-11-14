# Serverless image pipeline for Lumen Photo Co.

In mid-2024, I worked with **Lumen Photo Co.** on a fixed-scope build to improve how their media assets were processed and delivered. Their image flow needed to handle uploads reliably, generate multiple output sizes, add watermarks, and make those files available quickly without turning image handling into a maintenance burden.

I designed and built a serverless pipeline around **AWS Lambda**, **AWS S3**, **Sharp**, **Node.js**, and **CloudFront**. The core idea was simple: once an image was uploaded to storage, it would automatically kick off a Lambda function that handled the transformation work. That function created the required web-ready sizes, applied watermarks, and saved the processed versions back to S3 for delivery through the CDN.

This approach kept the system lightweight and scalable. Instead of running a dedicated image server, the processing logic lived in a small Node.js function that only ran when needed. Sharp handled the image manipulation efficiently, and CloudFront made the final assets fast to serve to end users. I focused on keeping the pipeline predictable, so each upload followed the same path from source file to optimized outputs.

A simplified version of the processing flow looked like this:

```js
const sharp = require("sharp");

exports.handler = async (event) => {
  const key = event.Records[0].s3.object.key;

  const image = await sharp(`/tmp/${key}`);
  await image
    .resize({ width: 1200 })
    .composite([{ input: "watermark.png", gravity: "southeast" }])
    .toFile(`/tmp/web-${key}`);
};
```

The result was a system that processed a large volume of images while reducing operational overhead. Over the course of the project, the pipeline handled **2.3M images processed**, and **hosting costs down 61%**. For Lumen Photo Co., that meant a cleaner backend for media delivery, faster asset handling, and a more cost-effective way to support ongoing image workloads.

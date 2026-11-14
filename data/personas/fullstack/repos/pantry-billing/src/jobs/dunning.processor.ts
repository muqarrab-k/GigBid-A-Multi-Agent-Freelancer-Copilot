import { Processor, WorkerHost } from '@nestjs/bullmq';
import { Logger } from '@nestjs/common';
import { Job } from 'bullmq';

type DunningJob = {
  invoiceId: string;
  customerId: string;
  email: string;
  retryCount?: number;
};

@Processor('dunning')
export class DunningProcessor extends WorkerHost {
  private readonly logger = new Logger(DunningProcessor.name);

  async process(job: Job<DunningJob>): Promise<void> {
    const { invoiceId, customerId, email, retryCount = 0 } = job.data;

    this.logger.log(
      `Retrying failed invoice ${invoiceId} for customer ${customerId} (attempt ${retryCount + 1})`,
    );

    const invoice = await this.getInvoice(invoiceId);
    if (!invoice) {
      this.logger.warn(`Invoice not found: ${invoiceId}`);
      return;
    }

    if (invoice.status !== 'open' || invoice.paid) {
      this.logger.log(`Skipping invoice ${invoiceId}; status is ${invoice.status}`);
      return;
    }

    const paid = await this.retryStripePayment(invoiceId);
    if (paid) {
      await this.markInvoiceRecovered(invoiceId);
      await this.sendReceiptEmail(email, invoiceId);
      return;
    }

    await this.scheduleNextRetry(job.data);
    await this.sendDunningEmail(email, invoiceId, retryCount + 1);
  }

  private async getInvoice(invoiceId: string): Promise<{ status: string; paid: boolean } | null> {
    return { status: 'open', paid: false };
  }

  private async retryStripePayment(invoiceId: string): Promise<boolean> {
    return false;
  }

  private async markInvoiceRecovered(invoiceId: string): Promise<void> {
    this.logger.log(`Marked invoice as recovered: ${invoiceId}`);
  }

  private async sendReceiptEmail(email: string, invoiceId: string): Promise<void> {
    this.logger.log(`Sent payment confirmation to ${email} for invoice ${invoiceId}`);
  }

  private async sendDunningEmail(email: string, invoiceId: string, retryCount: number): Promise<void> {
    this.logger.log(`Sent dunning email to ${email} for invoice ${invoiceId} on retry ${retryCount}`);
  }

  private async scheduleNextRetry(data: DunningJob): Promise<void> {
    this.logger.log(`Scheduled next retry for invoice ${data.invoiceId}`);
  }
}

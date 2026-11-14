import { Injectable, Logger, NotFoundException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import Stripe from 'stripe';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';

type LegacyPlan = 'starter' | 'pro' | 'team';

@Injectable()
export class BillingService {
  private readonly logger = new Logger(BillingService.name);
  private readonly stripe: Stripe;

  constructor(
    private readonly configService: ConfigService,
    @InjectRepository(Object) private readonly billingRepository: Repository<any>,
  ) {
    this.stripe = new Stripe(this.configService.get<string>('STRIPE_SECRET_KEY') ?? '', {
      apiVersion: '2024-06-20',
    });
  }

  private readonly planMap: Record<LegacyPlan, string> = {
    starter: 'price_starter_monthly',
    pro: 'price_pro_monthly',
    team: 'price_team_monthly',
  };

  async createSubscription(userId: string, legacyPlan: LegacyPlan, customerId: string) {
    const price = this.planMap[legacyPlan];
    if (!price) throw new NotFoundException(`Unknown plan: ${legacyPlan}`);

    const subscription = await this.stripe.subscriptions.create({
      customer: customerId,
      items: [{ price }],
      payment_behavior: 'default_incomplete',
      expand: ['latest_invoice.payment_intent'],
    });

    await this.billingRepository.save({
      userId,
      customerId,
      legacyPlan,
      stripeSubscriptionId: subscription.id,
      status: subscription.status,
    });

    this.logger.log(`Created subscription for user ${userId} on plan ${legacyPlan}`);
    return subscription;
  }

  async getMappedPrice(legacyPlan: LegacyPlan): Promise<string> {
    const price = this.planMap[legacyPlan];
    if (!price) throw new NotFoundException(`Unknown plan: ${legacyPlan}`);
    return price;
  }
}

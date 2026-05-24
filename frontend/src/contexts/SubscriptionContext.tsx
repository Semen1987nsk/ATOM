'use client';

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { api, ApiError } from '@/lib/apiClient';
import { useAuth } from '@/contexts/AuthContext';

// ==================== TYPES ====================

export type SubscriptionStatus =
  | 'none'
  | 'trial_active'
  | 'trial_expired'
  | 'free_plus'
  | 'pro_active'
  | 'corporate_active';

export type Capability =
  | 'api_sync'
  | 'new_ai_insight'
  | 'live_mae_mfe'
  | 'trade_replay_all'
  | 'optimal_f_live'
  | 'multi_account'
  | 'pdf_unlimited';

export interface SubscriptionStatusPayload {
  status: SubscriptionStatus;
  trial_started_at: string | null;
  trial_ended_at: string | null;
  trial_days_left: number | null;
  trial_summary_shown: boolean;
  frozen_at: string | null;
  capabilities: Capability[];
}

interface SubscriptionContextType {
  subscription: SubscriptionStatusPayload | null;
  isLoading: boolean;
  isProLike: boolean;
  isTrialActive: boolean;
  isFrozen: boolean;
  daysLeft: number | null;
  can: (capability: Capability) => boolean;
  refresh: () => Promise<void>;
  markTrialSummaryShown: () => Promise<void>;
}

// ==================== CONTEXT ====================

const SubscriptionContext = createContext<SubscriptionContextType | undefined>(undefined);

const PRO_LIKE_STATUSES: SubscriptionStatus[] = ['trial_active', 'pro_active', 'corporate_active'];
const POST_TRIAL_STATUSES: SubscriptionStatus[] = ['trial_expired', 'free_plus'];

export function SubscriptionProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [subscription, setSubscription] = useState<SubscriptionStatusPayload | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchStatus = useCallback(async () => {
    if (!isAuthenticated) {
      setSubscription(null);
      setIsLoading(false);
      return;
    }
    try {
      const data = await api.get<SubscriptionStatusPayload>('/subscription/status');
      setSubscription(data);
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 401)) {
        // Endpoint может ещё не существовать в backend — это OK на этом этапе.
        // SubscriptionContext деградирует в read-only режим без статуса.
        console.warn('[Subscription] Failed to fetch status:', error);
      }
      setSubscription(null);
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated]);

  useEffect(() => {
    void fetchStatus();
  }, [fetchStatus]);

  const markTrialSummaryShown = useCallback(async () => {
    try {
      await api.post('/subscription/trial-summary-shown', { body: {} });
      await fetchStatus();
    } catch (error) {
      console.warn('[Subscription] Failed to mark trial summary shown:', error);
    }
  }, [fetchStatus]);

  const isProLike = !!subscription && PRO_LIKE_STATUSES.includes(subscription.status);
  const isTrialActive = subscription?.status === 'trial_active';
  const isFrozen = !!subscription && POST_TRIAL_STATUSES.includes(subscription.status);

  const can = useCallback(
    (capability: Capability) => {
      if (!subscription) return false;
      return subscription.capabilities.includes(capability);
    },
    [subscription],
  );

  const value: SubscriptionContextType = {
    subscription,
    isLoading,
    isProLike,
    isTrialActive,
    isFrozen,
    daysLeft: subscription?.trial_days_left ?? null,
    can,
    refresh: fetchStatus,
    markTrialSummaryShown,
  };

  return (
    <SubscriptionContext.Provider value={value}>{children}</SubscriptionContext.Provider>
  );
}

// ==================== HOOK ====================

export function useSubscription(): SubscriptionContextType {
  const context = useContext(SubscriptionContext);
  if (context === undefined) {
    throw new Error('useSubscription must be used within a SubscriptionProvider');
  }
  return context;
}

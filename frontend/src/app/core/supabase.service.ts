import { Injectable } from '@angular/core';
import {
  AuthenticationDetails,
  CognitoUser,
  CognitoUserPool,
  CognitoUserSession
} from 'amazon-cognito-identity-js';
import { environment } from '../../environments/environment';

type AuthError = { message: string } | null;

interface CompatibleSession {
  access_token: string;
  user: {
    id: string;
    email: string;
    app_metadata: { roles: string[]; tenant_id?: string };
  };
}

/** Cognito-backed compatibility facade for the existing client.auth calls. */
@Injectable({ providedIn: 'root' })
export class SupabaseService {
  private readonly pool = new CognitoUserPool({
    UserPoolId: environment.cognitoUserPoolId,
    ClientId: environment.cognitoAppClientId
  });

  readonly client = {
    auth: {
      getSession: () => this.getSession(),
      signInWithPassword: (credentials: { email: string; password: string }) =>
        this.signInWithPassword(credentials.email, credentials.password),
      signOut: () => this.signOut(),
      resetPasswordForEmail: (email: string) => this.resetPasswordForEmail(email)
    }
  };

  private compatibleSession(session: CognitoUserSession): CompatibleSession {
    const payload = session.getIdToken().decodePayload() as Record<string, unknown>;
    const rawRoles = payload['custom:roles'];
    let roles: string[] = [];
    if (Array.isArray(rawRoles)) {
      roles = rawRoles.map(String);
    } else if (typeof rawRoles === 'string') {
      try {
        const parsed = JSON.parse(rawRoles);
        roles = Array.isArray(parsed) ? parsed.map(String) : [];
      } catch {
        roles = rawRoles.split(',').map(role => role.trim()).filter(Boolean);
      }
    }
    return {
      // The ID token carries the tenant and role claims validated by API Gateway.
      access_token: session.getIdToken().getJwtToken(),
      user: {
        id: String(payload['custom:user_id'] ?? payload['sub'] ?? ''),
        email: String(payload['email'] ?? ''),
        app_metadata: {
          roles,
          tenant_id: payload['custom:tenant_id'] ? String(payload['custom:tenant_id']) : undefined
        }
      }
    };
  }

  private getSession(): Promise<{ data: { session: CompatibleSession | null }; error: AuthError }> {
    const user = this.pool.getCurrentUser();
    if (!user) return Promise.resolve({ data: { session: null }, error: null });
    return new Promise(resolve => {
      user.getSession((error: Error | null, session: CognitoUserSession | null) => {
        if (error || !session?.isValid()) {
          resolve({ data: { session: null }, error: error ? { message: error.message } : null });
          return;
        }
        resolve({ data: { session: this.compatibleSession(session) }, error: null });
      });
    });
  }

  private signInWithPassword(email: string, password: string): Promise<{
    data: { session: CompatibleSession | null };
    error: AuthError;
  }> {
    const user = new CognitoUser({ Username: email, Pool: this.pool });
    const details = new AuthenticationDetails({ Username: email, Password: password });
    return new Promise(resolve => {
      const success = (session: CognitoUserSession) =>
        resolve({ data: { session: this.compatibleSession(session) }, error: null });
      const failure = (error: Error) =>
        resolve({ data: { session: null }, error: { message: error.message } });
      user.authenticateUser(details, {
        onSuccess: success,
        onFailure: failure,
        newPasswordRequired: () => user.completeNewPasswordChallenge(password, {}, {
          onSuccess: success,
          onFailure: failure
        })
      });
    });
  }

  private async signOut(): Promise<{ error: AuthError }> {
    this.pool.getCurrentUser()?.signOut();
    return { error: null };
  }

  private resetPasswordForEmail(email: string): Promise<{ error: AuthError }> {
    const user = new CognitoUser({ Username: email, Pool: this.pool });
    return new Promise(resolve => {
      user.forgotPassword({
        onSuccess: () => resolve({ error: null }),
        onFailure: (error: Error) => resolve({ error: { message: error.message } }),
        inputVerificationCode: () => resolve({ error: null })
      });
    });
  }
}

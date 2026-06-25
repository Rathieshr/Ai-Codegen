import * as SDK from 'azure-devops-extension-sdk';

export class UserService {
  public static async getAccessToken(): Promise<string> {
    return await SDK.getAccessToken();
  }

  public static getUser(): { name: string; email?: string } {
    const user = SDK.getUser();
    return { name: user.displayName, email: user.name };
  }
}

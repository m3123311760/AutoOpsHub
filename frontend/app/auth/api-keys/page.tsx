import { Header } from "@/components/header";
import { Sidebar } from "@/components/sidebar";
import { ApiKeysContent } from "@/components/api-keys-content";

export default function ApiKeysPage() {
  return (
    <div className="min-h-screen">
      <Sidebar />
      <main className="pl-64">
        <Header title="API Key" description="管理外部系统访问 AutoOpsHub 的认证凭据" />
        <div className="p-6">
          <ApiKeysContent />
        </div>
      </main>
    </div>
  );
}

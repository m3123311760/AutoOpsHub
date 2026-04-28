import { Sidebar } from "@/components/sidebar";
import { Header } from "@/components/header";
import { SettingsContent } from "@/components/settings-content";

interface SettingsPageProps {
  params: Promise<{
    workpiece: string;
  }>;
}

export default async function SettingsPage({ params }: SettingsPageProps) {
  const { workpiece } = await params;
  const decodedName = decodeURIComponent(workpiece);

  return (
    <div className="min-h-screen">
      <Sidebar currentWorkpiece={decodedName} />
      <main className="pl-64">
        <Header title="设置" description={`${decodedName} 的工作区设置`} />
        <div className="p-6">
          <SettingsContent workpiece={decodedName} />
        </div>
      </main>
    </div>
  );
}

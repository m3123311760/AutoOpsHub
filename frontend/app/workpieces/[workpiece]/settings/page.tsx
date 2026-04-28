import { Sidebar } from "@/components/sidebar";
import { Header } from "@/components/header";
import { SettingsContent } from "@/components/settings-content";
import { workpieceRouteParam } from "@/lib/routes";

interface SettingsPageProps {
  params: Promise<{
    workpiece: string;
  }>;
}

export default async function SettingsPage({ params }: SettingsPageProps) {
  const { workpiece } = await params;
  const workpieceName = workpieceRouteParam(workpiece);

  return (
    <div className="min-h-screen">
      <Sidebar currentWorkpiece={workpieceName} />
      <main className="pl-64">
        <Header title="设置" description={`${workpieceName} 的工作区设置`} />
        <div className="p-6">
          <SettingsContent workpiece={workpieceName} />
        </div>
      </main>
    </div>
  );
}

import { Sidebar } from "@/components/sidebar";
import { Header } from "@/components/header";
import { RunbooksContent } from "@/components/runbooks-content";

interface RunbooksPageProps {
  params: Promise<{
    workpiece: string;
  }>;
}

export default async function RunbooksPage({ params }: RunbooksPageProps) {
  const { workpiece } = await params;
  const decodedName = decodeURIComponent(workpiece);

  return (
    <div className="min-h-screen">
      <Sidebar currentWorkpiece={decodedName} />
      <main className="pl-64">
        <Header title="运行手册" description={`${decodedName} 的运行手册管理`} />
        <div className="p-6">
          <RunbooksContent workpiece={decodedName} />
        </div>
      </main>
    </div>
  );
}

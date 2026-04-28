import { Sidebar } from "@/components/sidebar";
import { Header } from "@/components/header";
import { TasksContent } from "@/components/tasks-content";

interface TasksPageProps {
  params: Promise<{
    workpiece: string;
  }>;
}

export default async function TasksPage({ params }: TasksPageProps) {
  const { workpiece } = await params;
  const decodedName = decodeURIComponent(workpiece);

  return (
    <div className="min-h-screen">
      <Sidebar currentWorkpiece={decodedName} />
      <main className="pl-64">
        <Header title="任务" description={`${decodedName} 的任务管理`} />
        <div className="p-6">
          <TasksContent workpiece={decodedName} />
        </div>
      </main>
    </div>
  );
}

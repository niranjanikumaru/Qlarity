import InteractiveNebulaShader from '@/components/ui/liquid-shader';
const settings = { hasActiveReminders: false, hasUpcomingReminders: false, disableCenterDimming: false };
export default function Demo(props: Partial<typeof settings>) {
  const s = { ...settings, ...props };
  return <div className="h-screen w-screen"><InteractiveNebulaShader {...s}/></div>;
}

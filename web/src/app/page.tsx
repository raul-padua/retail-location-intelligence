import { Workspace } from "@/components/Workspace";
import { SessionProvider } from "@/lib/session";

export default function Home() {
  return (
    <SessionProvider>
      <Workspace />
    </SessionProvider>
  );
}

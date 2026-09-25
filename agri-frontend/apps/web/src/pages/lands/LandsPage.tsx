import { useSession } from "@agri/core";
import { AgentLands } from "./AgentLands";
import { FarmerLands } from "./FarmerLands";

export function LandsPage() {
  const { user } = useSession();
  return user?.role === "farmer" ? <FarmerLands /> : <AgentLands />;
}

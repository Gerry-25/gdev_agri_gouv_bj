export type Role = "farmer" | "buyer" | "state_agent" | "state_supervisor";

export const FIELD_ROLES: Role[] = ["farmer", "buyer"];
export const AGENT_ROLES: Role[] = ["state_agent", "state_supervisor"];

export const isFieldRole = (role?: string | null) => !!role && (FIELD_ROLES as string[]).includes(role);
export const isAgentRole = (role?: string | null) => !!role && (AGENT_ROLES as string[]).includes(role);

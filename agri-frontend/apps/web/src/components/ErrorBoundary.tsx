import { Component, type ErrorInfo, type ReactNode } from "react";
import { Alert, Button } from "./ui";

/** Affiche un message au lieu d'une page blanche si un écran plante (donnée inattendue, etc.). */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Erreur d'affichage", error, info.componentStack);
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="space-y-3">
        <Alert tone="error">Cet écran a rencontré un problème. Vos données ne sont pas perdues.</Alert>
        <Button variant="outline" onClick={() => this.setState({ error: null })}>Réessayer</Button>
      </div>
    );
  }
}

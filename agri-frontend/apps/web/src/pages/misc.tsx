import { db, discardItem, formatRelative, processOutbox, retryItem, useSession } from "@agri/core";
import { useLiveQuery } from "dexie-react-hooks";
import { Link } from "react-router-dom";
import { Alert, Button, Card, CardHeader } from "../components/ui";
import { tabsFor } from "../lib/nav";
import { useOnline } from "../lib/useOnline";

export function MorePage() {
  const { user } = useSession();
  return (
    <Card>
      <CardHeader title="Toutes les rubriques" />
      <ul className="divide-y divide-neutral-100">
        {tabsFor(user?.role).map((t) => (
          <li key={t.label}>
            <Link to={t.to} className="flex items-center gap-3 py-3 text-base text-neutral-800 hover:text-emerald-800">
              <t.icon className="w-5 h-5 text-emerald-800" aria-hidden /> {t.label}
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function OutboxPage() {
  const online = useOnline();
  const items = useLiveQuery(() => db.outbox.orderBy("createdAt").toArray(), [], []);
  return (
    <Card>
      <CardHeader title="Envois en attente" />
      {items.length === 0 ? (
        <p className="text-sm text-neutral-600">Tout est envoyé.</p>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-neutral-600">Ces saisies sont gardées sur le téléphone et partiront dès que le réseau revient.</p>
          {online && <Button variant="soft" onClick={() => processOutbox()}>Envoyer maintenant</Button>}
          <ul className="space-y-2">
            {items.map((item) => (
              <li key={item.id} className={`p-3 border rounded-lg space-y-2 ${item.status === "failed" ? "border-red-300" : "border-neutral-200"}`}>
                <div className="flex justify-between gap-2 text-sm">
                  <span className="font-semibold">{item.label}</span>
                  <span className="text-neutral-500">{formatRelative(new Date(item.createdAt))}</span>
                </div>
                {item.status === "failed" && <Alert tone="error">Refusé par le serveur : {item.lastError}</Alert>}
                <div className="flex gap-2">
                  {item.status === "failed" && <Button variant="outline" onClick={() => retryItem(item.id!)}>Réessayer</Button>}
                  <Button variant="danger" onClick={() => discardItem(item.id!)}>Supprimer</Button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

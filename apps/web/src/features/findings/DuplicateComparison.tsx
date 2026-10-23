import type { Evidence } from "../../lib/api";

type PurchaseFacts = {
  purchase_id: string;
  supplier_id: string;
  product_id: string;
  product_name: string | null;
  purchase_date: string;
  quantity: string;
  unit_of_measure: string | null;
  unit_price: string;
  declared_total: string;
  currency: string;
  import_id: string;
};

const fields: { label: string; key: keyof PurchaseFacts }[] = [
  { label: "Fornecedor", key: "supplier_id" },
  { label: "Produto", key: "product_id" },
  { label: "Data da compra", key: "purchase_date" },
  { label: "Quantidade", key: "quantity" },
  { label: "Unidade", key: "unit_of_measure" },
  { label: "Preço unitário", key: "unit_price" },
  { label: "Total declarado", key: "declared_total" },
  { label: "Moeda", key: "currency" },
];

function purchaseFrom(item: Evidence): PurchaseFacts | null {
  const value = item.data.purchase;
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const purchase = value as Record<string, unknown>;
  if (typeof purchase.purchase_id !== "string" || typeof purchase.product_id !== "string")
    return null;
  return purchase as PurchaseFacts;
}

// The comparison explains the deterministic alert even when the optional model is unavailable.
export function DuplicateComparison({ evidence }: { evidence: Evidence[] }) {
  const pair = evidence.map(purchaseFrom);
  if (pair.length !== 2 || !pair[0] || !pair[1]) return null;
  const [first, second] = pair as [PurchaseFacts, PurchaseFacts];
  const sameImport = first.import_id === second.import_id;
  const allMatch = fields.every(({ key }) => first[key] === second[key]);
  return (
    <div className="duplicate-comparison">
      <p>
        <strong>Possível compra duplicada.</strong> São duas compras com IDs diferentes
        ({" "}<strong>{first.purchase_id}</strong> e <strong>{second.purchase_id}</strong>),
        mas os campos abaixo coincidem. O produto é o mesmo ({first.product_id});
        o alerta não indica dois produtos diferentes.
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>Campo</th><th>{first.purchase_id}</th><th>{second.purchase_id}</th></tr>
          </thead>
          <tbody>
            {fields.map(({ label, key }) => (
              <tr key={key}>
                <th scope="row">{label}</th>
                <td>{first[key] ?? "Não informado"}</td>
                <td>{second[key] ?? "Não informado"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted">
        {sameImport
          ? "As duas compras vieram da mesma importação."
          : "As compras vieram de importações diferentes."}{" "}
        {allMatch
          ? "A igualdade desses dados é o motivo do alerta."
          : "Há campos diferentes; confira as evidências antes de concluir."}
      </p>
      <p>
        <strong>Ainda não é um erro confirmado.</strong> Dois pedidos legítimos podem ter
        os mesmos dados. Confira os números dos pedidos, as notas fiscais, os
        recebimentos e eventuais pagamentos para decidir se uma compra foi
        registrada duas vezes.
      </p>
    </div>
  );
}

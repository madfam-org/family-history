import { notFound } from "next/navigation";

export default function UnknownAppPath(): never {
  notFound();
}

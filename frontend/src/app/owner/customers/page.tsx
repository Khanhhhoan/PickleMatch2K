import { redirect } from "next/navigation";

export default function CustomersRedirect() {
  redirect("/owner/dashboard");
}

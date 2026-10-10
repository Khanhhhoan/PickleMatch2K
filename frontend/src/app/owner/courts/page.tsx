import { redirect } from "next/navigation";

export default function CourtsRedirect() {
  redirect("/owner/venues?tab=courts_pricing");
}

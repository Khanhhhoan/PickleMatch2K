import { redirect } from "next/navigation";

export default function StaffRedirect() {
  redirect("/owner/venues?tab=staff");
}

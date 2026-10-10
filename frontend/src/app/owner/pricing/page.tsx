import { redirect } from "next/navigation";

export default function PricingRedirect() {
  redirect("/owner/venues?tab=courts_pricing&modal=price");
}

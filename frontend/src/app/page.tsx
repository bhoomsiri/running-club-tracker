import { redirect } from "next/navigation";

/**
 * `/` is a doorway, not a page. The middleware protects it, so anyone who gets this far
 * is signed in and belongs on the dashboard; anyone who is not was sent to /sign-in
 * before this ever ran.
 */
export default function Home() {
  redirect("/dashboard");
}

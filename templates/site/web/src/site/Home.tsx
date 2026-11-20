/**
 * The home page: the site's name and description (Admin, Settings, Site).
 * Its server copy is `backend/app/site/pages.py`'s answer for `/`: change both
 * together, so the words a crawler reads are the words a person sees.
 */
import { Seo, useSite } from "@/kernel";

export default function Home() {
  const site = useSite();
  if (site === undefined) return null;
  return (
    <>
      <Seo title={site.name} description={site.description} path="/" type="website" />
      <h1>{site.name}</h1>
      {site.description ? <p>{site.description}</p> : null}
    </>
  );
}

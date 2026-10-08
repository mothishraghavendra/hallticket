# Deploy on Vercel

The FastAPI application is configured as a Vercel Python function. Vercel
serves the mounted static assets from its CDN and bundles the PDF template and
Jinja templates with the function.

## Deploy from GitHub

1. Push the repository to GitHub after confirming local student data and photos
   are excluded from the commit.
2. In Vercel, choose **Add New Project** and import the repository.
3. Set the Root Directory to the repository root. Keep the detected Python
   framework settings and deploy.
4. Test the deployed home page, `/health`, and a generated PDF.

The app accepts photos up to 4 MB because Vercel Functions limit request bodies
to 4.5 MB, including multipart form data.

## Runtime behavior

Vercel's filesystem is not persistent. The generated-name registry is therefore
disabled there; names are still recorded when running locally or in Docker.
Use a managed database if deployment needs durable records.

The application has no user authentication. Treat a deployment as public and
do not enter real student data until access control and abuse protection are
configured for the Vercel project.

For local Vercel emulation, install the Vercel CLI and run `vercel dev` from the
repository root.
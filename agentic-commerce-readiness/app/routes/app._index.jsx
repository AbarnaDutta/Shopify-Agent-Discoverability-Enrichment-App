import { useEffect, useState } from "react";
import { boundary } from "@shopify/shopify-app-react-router/server";
import { authenticate } from "../shopify.server";

export const loader = async ({ request }) => {
  const { session } = await authenticate.admin(request);

  const shopDomain = session.shop;
  const accessToken = session.accessToken;

  if (!shopDomain || !accessToken) {
    throw new Response("Shopify session is missing.", {
      status: 500,
    });
  }

  const backendUrl = "https://geo.properoapps.in/api";

  const response = await fetch(
    `${backendUrl}/shopify-app/report-requests`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        email: "shopify-app@propero.in",
        shop_domain: shopDomain,
        access_token: accessToken,
        language: "English",
      }),
    },
  );

  const responseText = await response.text();

  if (!response.ok) {
  console.error(
    "Backend report request failed:",
    response.status,
    responseText,
  );

  throw new Response(
    `Backend error ${response.status}: ${responseText}`,
    {
      status: 500,
    },
  );
}

  let result;

  try {
    result = JSON.parse(responseText);
  } catch {
    throw new Response(
      "Backend returned an invalid response.",
      {
        status: 500,
      },
    );
  }

  return {
    job: result,
    backendUrl,
  };
};

export default function Index({ loaderData }) {
  const { job, backendUrl } = loaderData;

  const [status, setStatus] = useState(job.status);
  const [error, setError] = useState(job.error || null);

  useEffect(() => {
    if (
      status === "completed" ||
      status === "failed"
    ) {
      return;
    }

    const checkStatus = async () => {
      try {
        const response = await fetch(
          `${backendUrl}/report-requests/${job.job_id}`,
        );

        if (!response.ok) {
          throw new Error(
            `Status check failed: ${response.status}`,
          );
        }

        const result = await response.json();

        setStatus(result.status);

        if (result.error) {
          setError(result.error);
        }
      } catch (err) {
        console.error("Failed to check job status:", err);
      }
    };

    const interval = setInterval(
      checkStatus,
      3000,
    );

    return () => clearInterval(interval);
  }, [status, job.job_id, backendUrl]);

  return (
    <s-page heading="Agentic Commerce Readiness">
      <s-section heading="Catalog Audit">

        {status === "queued" && (
          <s-paragraph>
            Audit queued. Waiting for processing to start...
          </s-paragraph>
        )}

        {status === "processing" && (
          <s-paragraph>
            Audit in progress. Your Shopify products are
            currently being analyzed...
          </s-paragraph>
        )}

        {status === "completed" && (
          <s-paragraph>
            ✓ Audit completed successfully.
          </s-paragraph>
        )}

        {status === "failed" && (
          <s-paragraph>
            ✗ Audit failed.
            {error ? ` Error: ${error}` : ""}
          </s-paragraph>
        )}

      </s-section>
    </s-page>
  );
}

export const headers = (headersArgs) => {
  return boundary.headers(headersArgs);
};
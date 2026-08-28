import { useState } from "react";

export default function Audits() {
  const [showModal, setShowModal] = useState(false);

  return (
    <div className="min-h-screen bg-[#f8f8f6] p-8">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-[#063f3a]">
            Audits
          </h1>

          <p className="mt-1 text-sm text-[#71807d]">
            Create and manage your store audits.
          </p>
        </div>

        <button
          type="button"
          onClick={() => setShowModal(true)}
          className="rounded-xl bg-[#f59a18] px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-[#df870c]"
        >
          + Add Audit
        </button>
      </div>

      {/* Audit list */}
      <div className="rounded-2xl border border-[#e7e5df] bg-white shadow-sm">
        <div className="border-b border-[#eeeae2] px-6 py-5">
          <h2 className="font-semibold text-[#063f3a]">
            Your Audits
          </h2>
        </div>

        {/* Temporary empty state */}
        <div className="px-6 py-16 text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-xl bg-[#fff1dc] text-2xl text-[#f59a18]">
            +
          </div>

          <h3 className="mt-5 font-semibold text-[#063f3a]">
            No audits created yet
          </h3>

          <p className="mt-2 text-sm text-[#71807d]">
            Create an audit to analyze your Shopify store.
          </p>

          <button
            type="button"
            onClick={() => setShowModal(true)}
            className="mt-5 rounded-xl bg-[#063f3a] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#04332f]"
          >
            Create your first audit
          </button>
        </div>
      </div>

      {/* Add Audit Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white shadow-2xl">

            {/* Modal header */}
            <div className="flex items-center justify-between border-b border-[#eeeae2] px-6 py-5">
              <h2 className="text-xl font-bold text-[#063f3a]">
                Add Audit
              </h2>

              <button
                type="button"
                onClick={() => setShowModal(false)}
                className="text-2xl text-[#71807d] hover:text-[#063f3a]"
              >
                ×
              </button>
            </div>

            {/* Form */}
            <div className="space-y-5 p-6">

              <div>
                <label className="mb-2 block text-sm font-medium text-[#123d3a]">
                  Audit name
                </label>

                <input
                  type="text"
                  placeholder="My Store Audit"
                  className="w-full rounded-xl border border-[#dcd9d0] px-4 py-3 outline-none focus:border-[#063f3a]"
                />
              </div>

              <div>
                <label className="mb-2 block text-sm font-medium text-[#123d3a]">
                  Audit type
                </label>

                <select className="w-full rounded-xl border border-[#dcd9d0] px-4 py-3 outline-none focus:border-[#063f3a]">
                  <option>Full Commerce Audit</option>
                  <option>Catalog Audit</option>
                  <option>Agent Discovery Audit</option>
                </select>
              </div>

              <div>
                <label className="mb-2 block text-sm font-medium text-[#123d3a]">
                  Language
                </label>

                <select className="w-full rounded-xl border border-[#dcd9d0] px-4 py-3 outline-none focus:border-[#063f3a]">
                  <option value="en">English</option>
                  <option value="de">German</option>
                  <option value="fr">French</option>
                  <option value="es">Spanish</option>
                  <option value="ja">Japanese</option>
                </select>
              </div>

            </div>

            {/* Modal footer */}
            <div className="flex justify-end gap-3 border-t border-[#eeeae2] px-6 py-5">
              <button
                type="button"
                onClick={() => setShowModal(false)}
                className="rounded-xl border border-[#dcd9d0] px-5 py-2.5 text-sm font-semibold text-[#123d3a] hover:bg-[#f8f8f6]"
              >
                Cancel
              </button>

              <button
                type="button"
                onClick={() => {
                  setShowModal(false);
                }}
                className="rounded-xl bg-[#f59a18] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#df870c]"
              >
                Create Audit
              </button>
            </div>

          </div>
        </div>
      )}
    </div>
  );
}
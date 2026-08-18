import { useState } from 'react'
import { AppHeader } from '@/components/app-header'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { apiErrorMessage } from '@/lib/api-client'
import { createSale } from '@/services/api/salesApi'
import { getProduct } from '@/services/api/catalogApi'
import { t } from '@/i18n'
import { useAuth } from '@/features/auth/AuthProvider'
import { ProductSearch } from '@/features/sales/ProductSearch'
import { CartView } from '@/features/sales/CartView'
import { CrossSellSuggestion } from '@/features/sales/CrossSellSuggestion'
import { PaymentPanel } from '@/features/sales/PaymentPanel'
import { SaleConfirmation } from '@/features/sales/SaleConfirmation'
import { Ticket } from '@/features/sales/Ticket'
import { CloseShiftScreen } from '@/features/shift/CloseShiftScreen'
import { cartTotal, type CartLine } from '@/features/sales/cart'
import type { CashShift, PaymentMethod, Product, RelatedProductSummary, Sale } from '@/types/api'

interface SaleScreenProps {
  shift: CashShift
}

export function SaleScreen({ shift }: SaleScreenProps) {
  const { companySettings } = useAuth()
  const [cart, setCart] = useState<CartLine[]>([])
  const [method, setMethod] = useState<PaymentMethod>('CASH')
  const [cashReceived, setCashReceived] = useState('0')
  const [reference, setReference] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmingCancel, setConfirmingCancel] = useState(false)
  const [completed, setCompleted] = useState<{ sale: Sale; changeGiven: number } | null>(null)
  const [viewingTicket, setViewingTicket] = useState(false)
  const [closingShift, setClosingShift] = useState(false)
  const [crossSellItems, setCrossSellItems] = useState<RelatedProductSummary[]>([])

  function addToCart(product: Product) {
    setCart((current) => {
      const existing = current.find((line) => line.product.id === product.id)
      const next = existing
        ? current.map((line) => (line.product.id === product.id ? { ...line, quantity: line.quantity + 1 } : line))
        : [...current, { product, quantity: 1 }]

      const suggestions = product.related_products_detail.filter(
        (related) => !next.some((line) => line.product.id === related.id),
      )
      setCrossSellItems(suggestions)

      return next
    })
  }

  async function addSuggestionToCart(productId: number) {
    const product = await getProduct(productId)
    addToCart(product)
  }

  function changeQuantity(productId: number, quantity: number) {
    setCart((current) => current.map((line) => (line.product.id === productId ? { ...line, quantity } : line)))
  }

  function removeFromCart(productId: number) {
    setCart((current) => current.filter((line) => line.product.id !== productId))
  }

  function resetForNewSale() {
    setCart([])
    setMethod('CASH')
    setCashReceived('0')
    setReference('')
    setError(null)
    setCompleted(null)
    setViewingTicket(false)
    setCrossSellItems([])
  }

  function handleCancelSale() {
    setCart([])
    setCrossSellItems([])
    setError(null)
  }

  async function handleCharge() {
    if (cart.length === 0) {
      setError(t.sale.errorNoItems)
      return
    }
    const total = cartTotal(cart)
    setSubmitting(true)
    setError(null)
    try {
      const sale = await createSale({
        cash_shift: shift.id,
        details: cart.map((line) => ({
          product_id: line.product.id,
          quantity: line.quantity.toFixed(3),
          unit_price: line.product.sale_price,
        })),
        payments: [{ method, amount: total.toFixed(2), reference: reference || undefined }],
      })
      const changeGiven = method === 'CASH' ? Math.max(0, Number(cashReceived) - total) : 0
      setCompleted({ sale, changeGiven })
    } catch (err) {
      setError(apiErrorMessage(err, t.sale.errorGeneric))
    } finally {
      setSubmitting(false)
    }
  }

  if (closingShift) {
    return <CloseShiftScreen shift={shift} onCancel={() => setClosingShift(false)} />
  }

  if (completed && viewingTicket) {
    const businessName = companySettings?.business_name?.trim() || t.common.appName
    return (
      <Ticket
        sale={completed.sale}
        businessName={businessName}
        changeGiven={completed.changeGiven}
        onBack={() => setViewingTicket(false)}
      />
    )
  }

  if (completed) {
    return (
      <SaleConfirmation
        sale={completed.sale}
        changeGiven={completed.changeGiven}
        onNewSale={resetForNewSale}
        onViewTicket={() => setViewingTicket(true)}
      />
    )
  }

  const total = cartTotal(cart)

  return (
    <div className="flex min-h-svh flex-col bg-surface-muted">
      <AppHeader />

      <div className="flex flex-1 flex-col gap-6 p-6 lg:flex-row">
        <Card className="flex-1">
          <ProductSearch onSelect={addToCart} />
          <CrossSellSuggestion
            items={crossSellItems}
            onAdd={(id) => void addSuggestionToCart(id)}
            onDismiss={() => setCrossSellItems([])}
          />
          <div className="mt-8">
            <p className="text-lg font-medium text-ink mb-3">{t.sale.cart}</p>
            <CartView lines={cart} onChangeQuantity={changeQuantity} onRemove={removeFromCart} />
          </div>
        </Card>

        <Card className="w-full lg:w-96">
          <PaymentPanel
            total={total}
            method={method}
            onChangeMethod={setMethod}
            cashReceived={cashReceived}
            onChangeCashReceived={setCashReceived}
            reference={reference}
            onChangeReference={setReference}
            onCharge={handleCharge}
            submitting={submitting}
            disabled={cart.length === 0}
          />

          {error && (
            <p role="alert" className="mt-4 text-lg font-medium text-cancel">
              {error}
            </p>
          )}

          <Button
            type="button"
            variant="cancel"
            className="mt-4 w-full"
            onClick={() => setConfirmingCancel(true)}
            disabled={cart.length === 0}
          >
            {t.sale.cancelSale}
          </Button>

          <Button
            type="button"
            variant="neutral"
            className="mt-4 w-full"
            onClick={() => setClosingShift(true)}
          >
            {t.closeShift.openButton}
          </Button>
        </Card>
      </div>

      <ConfirmDialog
        open={confirmingCancel}
        message={t.sale.confirmCancelSale}
        confirmLabel={t.sale.confirmCancelSaleYes}
        onConfirm={handleCancelSale}
        onOpenChange={setConfirmingCancel}
      />
    </div>
  )
}

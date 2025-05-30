from django.http import JsonResponse
from django.shortcuts import render, redirect
from carts.models import CartItem
from store.models import Product
from .forms import OrderForm
import datetime
from .models import Order, OrderProduct,Payment
import  json
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.contrib import messages

def payments(request):
    body = json.loads(request.body)

    # Try to get order by order_number only, ignoring user (to avoid auth issues)
    try:
        order = Order.objects.get(order_number=body['orderID'], is_ordered=False)
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Order not found or already processed'}, status=404)

    # Check payment status
    if body['status'] != "COMPLETED":
        return JsonResponse({'error': 'Payment not completed'}, status=400)

    payment = Payment(
        user=order.user,
        payment_id=body['transID'],
        payment_method=body['payment_method'],
        amount_paid=order.order_total,
        status=body['status'],
    )
    payment.save()

    order.payment = payment
    order.is_ordered = True
    order.payment_status = 'Paid'
    order.status = 'Accepted'
    order.save()

    cart_items = CartItem.objects.filter(user=order.user)

    for item in cart_items:
        orderproduct = OrderProduct()
        orderproduct.order_id = order.id
        orderproduct.payment = payment
        orderproduct.user_id = order.user.id
        orderproduct.product_id = item.product_id
        orderproduct.quantity = item.quantity
        orderproduct.product_price = item.product.price
        orderproduct.ordered = True
        orderproduct.save()

        product_variation = item.variations.all()
        orderproduct.variations.set(product_variation)
        orderproduct.save()

        # Reduce stock
        product = Product.objects.get(id=item.product_id)
        product.stock -= item.quantity
        product.save()

    # Clear cart 
    CartItem.objects.filter(user=order.user).delete()

    # Send email
    mail_subject = 'Thank you for your order!'
    message = render_to_string('order_recieved_email.html', {
        'user': order.user,
        'order': order,
    })
    to_email = order.user.email
    send_email = EmailMessage(mail_subject, message, to=[to_email])
    send_email.send()

    data = {
        'order_number': order.order_number,
        'transID': payment.payment_id,
    }
    return JsonResponse(data)

def place_order(request, total=0, quantity=0):
    current_user = request.user

    # Fetch cart items for the current user
    cart_items = CartItem.objects.filter(user=current_user)
    cart_count = cart_items.count()

    # If the cart is empty, redirect to the store
    if cart_count <= 0:
        return redirect('store') 

    grand_total = 0
    tax = 0

    # Calculate the total price and quantity of items in the cart
    for cart_item in cart_items:
        total += (cart_item.product.price * cart_item.quantity)
        quantity += cart_item.quantity

    # Calculate tax (hardcoded as 2%)
    tax = (2 * total) / 100
    grand_total = total + tax

    # If the request method is POST, process the order form
    if request.method == 'POST':
        form = OrderForm(request.POST)
        if form.is_valid():
            # Store the billing information in the Orders table
            data = Order()
            data.user = current_user
            data.first_name = form.cleaned_data['first_name']
            data.last_name = form.cleaned_data['last_name']
            data.phone = form.cleaned_data['phone']
            data.email = form.cleaned_data['email']
            data.address_line_1 = form.cleaned_data['address_line_1']
            data.address_line_2 = form.cleaned_data['address_line_2']
            data.country = form.cleaned_data['country']
            data.state = form.cleaned_data['state']
            data.city = form.cleaned_data['city']
            data.order_note = form.cleaned_data['order_note']
            data.order_total = grand_total
            data.tax = tax
            data.ip = request.META.get('REMOTE_ADDR')  # Fixed the method call
            data.save()

            # Generate the order number
            yr = int(datetime.date.today().strftime('%Y'))
            dt = int(datetime.date.today().strftime('%d'))
            mt = int(datetime.date.today().strftime('%m'))
            d = datetime.date(yr, mt, dt)
            current_date = d.strftime('%Y%m%d')
            order_number = current_date + str(data.id)
            data.order_number = order_number
            data.save()

            # Get the selected payment method
            payment_method = form.cleaned_data.get('payment_method') or request.POST.get('payment_method')
            order = Order.objects.get(user=current_user, is_ordered=False, order_number=order_number)

            if payment_method == 'COD':
                # Mark order as complete immediately for COD
                order.is_ordered = True
                order.payment_method = 'COD'
                order.payment_status = 'Unpaid' 
                order.status = 'Accepted'  # Optional
                order.save()

                for item in cart_items:
                    order_product = OrderProduct()
                    order_product.order_id = order.id
                    order_product.user_id = current_user.id
                    order_product.product_id = item.product_id
                    order_product.quantity = item.quantity
                    order_product.product_price = item.product.price
                    order_product.ordered = True
                    order_product.save()

                    # Save variations
                    product_variation = item.variations.all()
                    order_product.variations.set(product_variation)
                    order_product.save()

                    # Reduce stock
                    product = Product.objects.get(id=item.product_id)
                    product.stock -= item.quantity
                    product.save()

                # Clear the cart
                CartItem.objects.filter(user=current_user).delete()

                # (Optional) Send email for COD
                mail_subject = 'Thank you for your COD order!'
                message = render_to_string('order_recieved_email.html', {
                    'user': request.user,
                    'order': order,
                })
                to_email = request.user.email
                send_email = EmailMessage(mail_subject, message, to=[to_email])
                send_email.send()

                messages.success(request, "Your COD order has been placed successfully!")
                return redirect('order_complete')  # optionally: add ?order_number=...&payment_id=...

            else:
                # Go to payments.html for PayPal
                context = {
                    'order': order,
                    'cart_items': cart_items,
                    'grand_total': grand_total,
                    'total': total,
                    'tax': tax,
                }
                return render(request, 'payments.html', context)

    return redirect('checkout')

def order_success_cod(request):
    current_user = request.user

    # Cart items fetch karo
    cart_items = CartItem.objects.filter(user=current_user)
    if cart_items.count() <= 0:
        return redirect('store')

    total = 0
    quantity = 0
    for cart_item in cart_items:
        total += (cart_item.product.price * cart_item.quantity)
        quantity += cart_item.quantity

    tax = (2 * total) / 100
    grand_total = total + tax

    if request.method == 'POST':
        form = OrderForm(request.POST)
        if form.is_valid():
            data = Order()
            data.user = current_user
            data.first_name = form.cleaned_data['first_name']
            data.last_name = form.cleaned_data['last_name']
            data.phone = form.cleaned_data['phone']
            data.email = form.cleaned_data['email']
            data.address_line_1 = form.cleaned_data['address_line_1']
            data.address_line_2 = form.cleaned_data['address_line_2']
            data.country = form.cleaned_data['country']
            data.state = form.cleaned_data['state']
            data.city = form.cleaned_data['city']
            data.order_note = form.cleaned_data['order_note']
            data.order_total = grand_total
            data.tax = tax
            data.ip = request.META.get('REMOTE_ADDR')
            
            data.is_ordered = True
            data.payment_status = 'Paid' 
            data.status = 'Accepted'  # Optional
            data.save()

            # Order number generate
            yr = int(datetime.date.today().strftime('%Y'))
            dt = int(datetime.date.today().strftime('%d'))
            mt = int(datetime.date.today().strftime('%m'))
            d = datetime.date(yr, mt, dt)
            current_date = d.strftime('%Y%m%d')
            order_number = current_date + str(data.id)
            data.order_number = order_number
            data.save()

            # Order product save karna
            for item in cart_items:
                order_product = OrderProduct()
                order_product.order_id = data.id
                order_product.user_id = current_user.id
                order_product.product_id = item.product_id
                order_product.quantity = item.quantity
                order_product.product_price = item.product.price
                order_product.ordered = True
                order_product.save()

                # Reduce stock
                product = Product.objects.get(id=item.product_id)
                product.stock -= item.quantity
                product.save()

            # Clear cart
            CartItem.objects.filter(user=current_user).delete()

            messages.success(request, "Your COD order has been placed successfully!")
            return redirect('order_complete')  # You should have this template
        else:
            messages.error(request, "Please correct the errors in the form.")
            return redirect('checkout')
    else:
        return redirect('checkout')

    
def order_complete(request):
    order_number = request.GET.get('order_number')
    transID = request.GET.get('payment_id')  # Might be None for COD

    try:
        order = Order.objects.get(order_number=order_number, is_ordered=True)
        ordered_products = OrderProduct.objects.filter(order_id=order.id)

        subtotal = 0 
        for i in ordered_products:
            subtotal += (i.product.price * i.quantity)

        # Use .filter().first() to avoid DoesNotExist error for COD
        payment = Payment.objects.filter(payment_id=transID).first()

        context = {
            'order': order,
            'ordered_products': ordered_products, 
            'order_number': order.order_number,
            'transID': transID if transID else "COD",
            'payment': payment,
            'subtotal': subtotal,
        }
        return render(request, 'order_complete.html', context)

    except Order.DoesNotExist:
        return redirect('index')
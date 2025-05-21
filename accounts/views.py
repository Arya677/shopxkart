from django.contrib import messages, auth
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from orders.models import Order, OrderProduct
from accounts.models import Account, UserProfile
from .forms import RegistrationForm, UserForm, UserProfileForm
from carts.views import _cart_id
from carts.models import Cart, CartItem
from django.contrib.auth import update_session_auth_hash
import requests

#verificaiton email
from django.contrib.sites.shortcuts import get_current_site
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMessage

def register(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            first_name = form.cleaned_data['first_name']
            last_name = form.cleaned_data['last_name']
            email = form.cleaned_data['email']
            phone_number = form.cleaned_data['phone_number']
            password = form.cleaned_data['password']

            # Create user
            user = Account.objects.create_user(
                username=username, 
                first_name=first_name, 
                last_name=last_name, 
                email=email, 
                password=password
            )
            user.phone_number = phone_number
            # user.is_active = False 
            user.save()

            # User Activation Email
            current_site = get_current_site(request)
            
            mail_subject = 'Activate your account'
            message = render_to_string('accounts/account_verification_email.html', {
                'user': user,
                'domain': current_site.domain,  
                'uid': urlsafe_base64_encode(force_bytes(user.pk)),
                'token': default_token_generator.make_token(user),
                'protocol': 'https' if request.is_secure() else 'http',
            })
            to_email = user.email
            send_email = EmailMessage(mail_subject, message, to=[to_email]) #from_email=settings.EMAIL_HOST_USER
            try:
                send_email.send(fail_silently=False)  # Email sending with error handling
                messages.success(request, 'Thank you for registering! Please check your email to verify your account.')
            except Exception as e:
                messages.error(request, f"Email could not be sent. Error: {e}")
            return redirect('/accounts/login/?command=verification&email='+email) 
    
    else:
        form = RegistrationForm()
    
    return render(request, 'accounts/register.html', {'form': form})

def activate(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = Account._default_manager.get(pk=uid)
    except (TypeError, ValueError, OverflowError, Account.DoesNotExist):
        user = None
        messages.error(request, 'Invalid activation link') 

    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        messages.success(request, 'Congratulations! Your account is now active.')
        return redirect('login')
    else:
        messages.error(request, 'Invalid activation link')
        return redirect('register')  # Redirect to prevent form resubmission

def login(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        user = auth.authenticate(email=email, password=password)

        if user is not None and user.is_active:
            try:
                cart = Cart.objects.get(cart_id=_cart_id(request))
                is_cart_item_exists = CartItem.objects.filter(cart=cart).exists()
                if is_cart_item_exists:
                    cart_item = CartItem.objects.filter(cart=cart)

                    product_variation = []
                    for item in cart_item:
                        variation = item.variations.all()
                        product_variation.append(list(variation))

                    cart_item  = CartItem.objects.filter(user=user)
                    ex_var_list = []    
                    id = []
                    for item in cart_item:
                        existing_variation = item.variations.all()
                        ex_var_list.append(list(existing_variation))
                        id.append(item.id)

                    for pr in product_variation:
                        if pr in ex_var_list:
                            index = ex_var_list.index(pr)
                            item_id = id[index]
                            item = CartItem.objects.get(id=item_id)
                            item.quantity += 1
                            item.user = user
                            item.save()
                        else:
                            cart_item = CartItem.objects.filter(cart=cart)
                            for item in cart_item:
                                item.user = user
                                item.save()
            except:
                pass
            auth.login(request, user)
            url = request.META.get('HTTP_REFEREL')
            try:
                querry = request.utils.urlparse( url ).querry
                params = dict(x.split('=') for x in querry.split('&'))
                if 'next' in params:
                    next_page = params['next'].replace(' ', '+')
                    return redirect(next_page) 
            except:
                return redirect('/')

        else:
            messages.error(request, 'Invalid credentials or account not active')
            return redirect('login')
    return render(request, 'accounts/login.html')


@login_required(login_url='login/')
def logout(request):
    auth.logout(request)
    messages.success(request, 'You have been logged out.')
    return redirect('login')

@login_required(login_url='login')
def dashboard(request):
    orders = Order.objects.order_by('-created_at').filter(user_id=request.user.id, is_ordered=True)
    orders_count = orders.count()

    try:
        userprofile = UserProfile.objects.get(user=request.user)
    except UserProfile.DoesNotExist:
        userprofile = None

    context = {
        'orders_count': orders_count, 
        'userprofile': userprofile,
    }
    return render(request, 'accounts/dashboard.html', context)

def forgotPassword(request):
    if request.method == 'POST':
        email = request.POST['email']
        if Account.objects.filter(email=email).exists():
            user = Account.objects.get(email__exact=email)

            current_site = get_current_site
            mail_subject = 'Reset your password'
            message = render_to_string('accounts/reset_password_email.html', {
                'user': user,
                'domain': current_site,  
                'uid': urlsafe_base64_encode(force_bytes(user.pk)),
                'token': default_token_generator.make_token(user),

            })
            to_email = email
            send_email = EmailMessage(mail_subject, message, to=[to_email]) 
            send_email.send()
            messages.success(request, 'Password reset link has been sent to your email.')
            return redirect('login')
        else:
            messages.error(request, 'Account does not exist')
            return redirect('forgotPassword')
    return render(request, 'accounts/forgotPassword.html')

def resetpassword_validate(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = Account._default_manager.get(pk=uid)
    except (TypeError, ValueError, OverflowError, Account.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        request.session['uid'] = uid
        messages.success(request, 'Please reset your password')
        return redirect('resetPassword')
    else:
        messages.error(request,'This link has been expired')
        return redirect('login')    

def resetPassword(request):
    if request.method == 'POST':
        password = request.POST['password']
        confirm_password = request.POST['confirm_password']

        if password == confirm_password:
            uid = request.session.get('uid')
            user = Account.objects.get(pk=uid)
            user.set_password(password)
            user.save()
            messages.success(request, 'Password reset successfully')
            return redirect('login')      
        else:   
            messages.error(request, 'Passwords do not match!')
            return redirect('resetPassword')
    else:
        return render(request, 'accounts/resetPassword.html')

@login_required(login_url='/login/')
def my_orders(request):
    orders = Order.objects.filter(user=request.user, is_ordered=True).order_by('-created_at')
    context = {
        'orders': orders,
    }
    return render(request, 'accounts/my_orders.html', context)

@login_required(login_url='/login/')
def edit_profile(request):
    #userprofile = get_object_or_404(UserProfile, user=request.user)
    try:
        userprofile = UserProfile.objects.get(user=request.user)
    except UserProfile.DoesNotExist:
        userprofile = None
    if request.method == 'POST':
        user_form = UserForm(request.POST, instance=request.user)
        profile_form = UserProfileForm(request.POST, request.FILES, instance=userprofile)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile = profile_form.save(commit=False)  # Prevent accidental save
            profile.user = request.user  # Explicitly assign the user
            profile.save()
            messages.success(request, 'Your profile has been updated successfully')
            return redirect('edit_profile')
            
    else:
        user_form = UserForm(instance=request.user)
        profile_form = UserProfileForm(instance=userprofile)
    context = {
        'user_form': user_form,
        'profile_form': profile_form,
        'userprofile': userprofile,
    }
    return render(request, 'accounts/edit_profile.html', context)

@login_required(login_url='/login/')
def change_password(request):
    if request.method == 'POST':
        current_password = request.POST['current_password']
        new_password = request.POST['new_password']
        confirm_password = request.POST['confirm_password']

        user = request.user  # No need to manually query the user

        if not user.check_password(current_password):
            messages.error(request, 'Your current password is incorrect')
            return redirect('change_password')

        if new_password != confirm_password:
            messages.error(request, 'New passwords do not match')
            return redirect('change_password')

        if len(new_password) < 8:
            messages.error(request, 'Password must be at least 8 characters long')
            return redirect('change_password')

        # Change the password
        user.set_password(new_password)
        user.save()

        # Keep the user logged in after changing password
        update_session_auth_hash(request, user)

        messages.success(request, 'Your password has been updated successfully')
        return redirect('dashboard')

    return render(request, 'accounts/change_password.html')

@login_required(login_url='/login/')
def order_detail(request, order_id):
    order_detail = OrderProduct.objects.filter(order__order_number=order_id)
    order = Order.objects.get(order_number=order_id)
    subtotal = 0 
    for i in order_detail:
        subtotal += i.product.price * i.quantity

    context = {
        'order_detail': order_detail,
        'order': order,
        'subtotal': subtotal,
    }
    return render(request, 'accounts/order_detail.html', context) 
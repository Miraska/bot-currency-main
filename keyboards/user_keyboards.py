from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

buttons = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text='Royalty', callback_data='royalty'),
            InlineKeyboardButton(text='Delivery', callback_data='delivery'),
        ],
        [
            InlineKeyboardButton(text='Payment', callback_data='payment'),
            InlineKeyboardButton(text='Operational', callback_data='operational'),
        ],
        [
            InlineKeyboardButton(text='Cashless', callback_data='cashless'),
            InlineKeyboardButton(text='Discount', callback_data='discount'),
        ],
        [
            InlineKeyboardButton(text='Aed_Usdt', callback_data='aedusdt')
        ]
    ]
)

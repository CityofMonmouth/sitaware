from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, TextAreaField, SelectField, SubmitField, BooleanField
from wtforms.fields import DateTimeLocalField, EmailField
from wtforms.validators import DataRequired, Length, Optional, Email, Regexp

CATEGORY_CHOICES = [
    ("incident", "Incident"),
    ("weather_road", "Weather / Road Conditions"),
    ("facility_equipment", "Facility / Equipment"),
    ("personnel", "Personnel"),
    ("training", "Training"),
    ("general", "General Notice"),
]

PRIORITY_CHOICES = [
    ("urgent", "Urgent"),
    ("advisory", "Advisory"),
    ("info", "Info"),
]

AGENCY_CHOICES = [
    ("City", "City"),
    ("County", "County"),
    ("PD", "Police Dept"),
]


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Sign In")


class AgencyAccessForm(FlaskForm):
    password = PasswordField("Agency Password", validators=[DataRequired()])
    submit = SubmitField("View Board (Read-Only)")


class PostForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=200)])
    category = SelectField("Category", choices=CATEGORY_CHOICES, validators=[DataRequired()])
    priority = SelectField("Priority", choices=PRIORITY_CHOICES, default="advisory", validators=[DataRequired()])
    body = TextAreaField("Details", validators=[DataRequired(), Length(max=8000)])
    expires_at = DateTimeLocalField(
        "Active Until (optional, defaults to 24 hrs)",
        format="%Y-%m-%dT%H:%M",
        validators=[Optional()],
    )
    notify_email = BooleanField("Email this update to the distribution list", default=True)
    submit = SubmitField("Post Update")


class UserForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(max=64)])
    display_name = StringField("Display Name", validators=[DataRequired(), Length(max=128)])
    agency = SelectField("Agency", choices=AGENCY_CHOICES)
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8)])
    role = SelectField("Role", choices=[("user", "User"), ("admin", "Admin")])
    submit = SubmitField("Create User")


class EditUserForm(FlaskForm):
    display_name = StringField("Display Name", validators=[DataRequired(), Length(max=128)])
    agency = SelectField("Agency", choices=AGENCY_CHOICES)
    role = SelectField("Role", choices=[("user", "User"), ("admin", "Admin")])
    password = PasswordField(
        "New Password (leave blank to keep current)",
        validators=[Optional(), Length(min=8)],
    )
    submit = SubmitField("Save Changes")


class SubscriberForm(FlaskForm):
    email = EmailField("Email Address", validators=[DataRequired(), Email(), Length(max=255)])
    label = StringField("Label (optional)", validators=[Optional(), Length(max=128)])
    submit = SubmitField("Add to List")


class SmsSubscriberForm(FlaskForm):
    phone = StringField(
        "Phone Number (E.164 format, e.g. +15551234567)",
        validators=[
            DataRequired(),
            Regexp(
                r"^\+[1-9]\d{7,14}$",
                message="Enter a valid phone number in E.164 format, e.g. +15551234567",
            ),
            Length(max=20),
        ],
    )
    label = StringField("Label (optional)", validators=[Optional(), Length(max=128)])
    submit = SubmitField("Add to List")


class EmergencyAlertForm(FlaskForm):
    message = TextAreaField(
        "What's happening?",
        validators=[DataRequired(), Length(max=500)],
    )
    submit = SubmitField("Send Emergency Alert")
